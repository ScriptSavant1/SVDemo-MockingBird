package com.mockingbird.stubs;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.tomakehurst.wiremock.client.ResponseDefinitionBuilder;
import com.github.tomakehurst.wiremock.extension.requestfilter.RequestFilterAction;
import com.github.tomakehurst.wiremock.extension.requestfilter.StubRequestFilterV2;
import com.github.tomakehurst.wiremock.http.Request;
import com.github.tomakehurst.wiremock.http.ResponseDefinition;
import com.github.tomakehurst.wiremock.stubbing.ServeEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Serves CA LISA operations recorded with too many same-URL captures for
 * static per-capture WireMock mappings to be the right fit (see
 * generator/lookup_table.py for the threshold and full rationale). Instead
 * of N WireMock StubMapping entries each carrying its own bodyPatterns
 * matcher — which WireMock evaluates sequentially against every mapping
 * sharing a URL, worst case O(N) XPath/JSONPath evaluations per request —
 * this filter holds one immutable, pre-built lookup table per route and
 * answers in O(1), regardless of whether that route has 10 captured
 * variants or 10,000.
 *
 * Registered into WireMock's own request pipeline via
 * WireMockConfiguration.extensions(...), the same mechanism
 * WsSecurityRequestFilter already uses. Request filters run before
 * WireMock's own stub matching, so a route this filter answers for never
 * touches WireMock's mapping registry at all — no StubMapping is ever
 * created for these URLs, and they never show up in "Loaded N stub
 * mappings" (see WireMockConfig.java's separate log line for this filter).
 *
 * Two kinds of route are supported, matching the two discriminator kinds
 * generator/lookup_table.py can produce:
 *   - Exact-URL, body-discriminated: one specific urlPath, the response is
 *     picked by a field extracted from the request body (an account name,
 *     a customer ID in the payload, ...).
 *   - URL-pattern, path-discriminated: a regex matching every captured
 *     URL's shape (e.g. "/customerinstructions/{id}/addressbook", where an
 *     ID is embedded in the path itself, not the body) — the response is
 *     picked by the one value the pattern's capture group extracts from
 *     the URL, with no body inspection at all. An earlier version of this
 *     generator only recognised the exact-URL case and silently used
 *     whichever URL the first capture happened to record for every
 *     scenario, discarding every other capture's distinct URL entirely.
 *
 * Performance/lifecycle notes, since this sits directly on the 10K+ TPS
 * request path:
 *   - All lookup tables are parsed once in the constructor into immutable
 *     collections. Nothing is ever added afterwards, so reads need no
 *     locking and there is nothing for the GC to chase beyond the one-time
 *     load — no caches, no eviction, no unbounded growth.
 *   - Discriminator extraction never builds a full DOM/object tree: XML
 *     uses a streaming StAX reader (stops at the first matching element,
 *     matching generator/lookup_table.py's contract that the discriminator
 *     is always a leaf element with a body-unique name) and JSON uses
 *     Jackson's streaming parser scanning only top-level fields. Both
 *     factories (XMLInputFactory, JsonFactory) are stateless configuration
 *     holders safe to share across threads — creating a reader/parser from
 *     them does not mutate the factory, the same pattern
 *     WsSecurityRequestFilter and Spring's own JSON handling already rely
 *     on — so no per-request or per-thread factory allocation is needed.
 *     URL-pattern routes need no body parsing at all — the discriminator
 *     comes straight out of the already-matched regex.
 *   - A request that doesn't match any registered route (the overwhelming
 *     majority of traffic on any given stub) costs one HashMap lookup for
 *     the exact-URL routes, plus a linear scan of the (typically very
 *     small — one per distinct path-templated operation) list of
 *     URL-pattern routes, before falling through to WireMock's normal
 *     handling.
 */
public class DynamicLookupRequestFilter implements StubRequestFilterV2 {

    private static final Logger log = LoggerFactory.getLogger(DynamicLookupRequestFilter.class);

    // Configuration-only holders — safe to share across concurrent requests;
    // creating a reader/parser from either does not mutate shared state.
    private static final XMLInputFactory XML_INPUT_FACTORY = buildXmlInputFactory();
    private static final JsonFactory JSON_FACTORY = new JsonFactory();

    private final Map<String, LookupRoute> exactRoutesByKey;
    private final List<LookupRoute> patternRoutes;

    public DynamicLookupRequestFilter() {
        List<LookupRoute> allRoutes = loadRoutes();
        Map<String, LookupRoute> exact = new HashMap<>();
        List<LookupRoute> patterns = new ArrayList<>();
        for (LookupRoute route : allRoutes) {
            if (route.urlPattern != null) {
                patterns.add(route);
            } else {
                exact.put(routeKey(route.method, route.urlPath), route);
            }
        }
        this.exactRoutesByKey = Collections.unmodifiableMap(exact);
        this.patternRoutes = Collections.unmodifiableList(patterns);

        int totalEntries = 0;
        for (LookupRoute route : allRoutes) {
            totalEntries += route.entries.size();
        }
        log.info("DynamicLookupRequestFilter: loaded {} route(s) ({} exact-URL, {} URL-pattern), {} total entries",
                allRoutes.size(), exact.size(), patterns.size(), totalEntries);
    }

    @Override
    public RequestFilterAction filter(Request request, ServeEvent serveEvent) {
        if (exactRoutesByKey.isEmpty() && patternRoutes.isEmpty()) {
            return RequestFilterAction.continueWith(request);
        }

        String method = request.getMethod().getName();
        String path = stripQuery(request.getUrl());

        LookupRoute route = exactRoutesByKey.get(routeKey(method, path));
        String discriminatorValue;

        if (route != null) {
            if (!headersMatch(request, route.requiredHeaders)) {
                return RequestFilterAction.continueWith(request);
            }
            discriminatorValue = route.extractBodyDiscriminator(request.getBodyAsString());
        } else {
            LookupRoute matchedPatternRoute = null;
            String extractedFromUrl = null;
            for (LookupRoute candidate : patternRoutes) {
                if (!candidate.method.equalsIgnoreCase(method)) {
                    continue;
                }
                Matcher m = candidate.urlPattern.matcher(path);
                if (m.matches() && headersMatch(request, candidate.requiredHeaders)) {
                    matchedPatternRoute = candidate;
                    extractedFromUrl = joinCaptureGroups(m);
                    break;
                }
            }
            route = matchedPatternRoute;
            discriminatorValue = extractedFromUrl;
        }

        if (route == null || discriminatorValue == null) {
            return RequestFilterAction.continueWith(request);
        }

        CannedResponse canned = route.entries.get(discriminatorValue);
        if (canned == null) {
            // Unrecognised value for a registered route — fall through to
            // WireMock's normal "no mapping matched" behaviour rather than
            // inventing a response for data we were never given.
            return RequestFilterAction.continueWith(request);
        }

        ResponseDefinitionBuilder builder = new ResponseDefinitionBuilder().withStatus(canned.status);
        for (Map.Entry<String, String> header : canned.headers.entrySet()) {
            builder.withHeader(header.getKey(), header.getValue());
        }
        if (canned.body != null) {
            builder.withBody(canned.body);
        }
        ResponseDefinition response = builder.build();
        return RequestFilterAction.stopWith(response);
    }

    @Override
    public boolean applyToAdmin() {
        return false;
    }

    @Override
    public boolean applyToStubs() {
        return true;
    }

    @Override
    public String getName() {
        return "dynamic-lookup-request-filter";
    }

    // ── route loading ─────────────────────────────────────────────────────

    private static List<LookupRoute> loadRoutes() {
        List<LookupRoute> result = new ArrayList<>();
        try {
            PathMatchingResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
            Resource[] resources = resolver.getResources("classpath*:lookup-tables/*.json");
            ObjectMapper mapper = new ObjectMapper();
            for (Resource resource : resources) {
                try (InputStream in = resource.getInputStream()) {
                    JsonNode root = mapper.readTree(in);
                    result.add(LookupRoute.fromJson(root));
                } catch (Exception e) {
                    log.warn("DynamicLookupRequestFilter: failed to load lookup table {}: {}",
                            resource.getFilename(), e.getMessage());
                }
            }
        } catch (IOException e) {
            log.warn("DynamicLookupRequestFilter: failed to scan classpath:/lookup-tables/: {}", e.getMessage());
        }
        return result;
    }

    private static String routeKey(String method, String urlPath) {
        return method.toUpperCase(java.util.Locale.ROOT) + " " + urlPath;
    }

    private static String stripQuery(String url) {
        int q = url.indexOf('?');
        return q >= 0 ? url.substring(0, q) : url;
    }

    // Must match ca_lisa_parser.py's _URL_SEGMENT_KEY_JOIN exactly — an
    // ASCII "unit separator", chosen because it's vanishingly unlikely to
    // appear in a real captured path segment.
    private static final String URL_SEGMENT_KEY_JOIN = "\u001F";

    /** Joins every capture group a URL-pattern route's regex matched, in
     * order, with URL_SEGMENT_KEY_JOIN — one group per varying path segment
     * (an operation with two IDs embedded in its path, e.g.
     * "/accounts/{acctId}/sub/{subId}", produces two groups). Reconstructs
     * exactly the composite key _detect_url_segment_pattern built on the
     * Python side, so a single- or multi-segment pattern route works
     * identically here without special-casing which case it is. */
    private static String joinCaptureGroups(Matcher m) {
        int count = m.groupCount();
        if (count == 0) {
            return null;
        }
        if (count == 1) {
            return m.group(1);
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 1; i <= count; i++) {
            if (i > 1) {
                sb.append(URL_SEGMENT_KEY_JOIN);
            }
            sb.append(m.group(i));
        }
        return sb.toString();
    }

    private static boolean headersMatch(Request request, Map<String, String> required) {
        for (Map.Entry<String, String> e : required.entrySet()) {
            String actual = request.getHeader(e.getKey());
            if (actual == null) {
                return false;
            }
            boolean caseInsensitive = e.getKey().equalsIgnoreCase("Content-Type");
            boolean matches = caseInsensitive ? actual.equalsIgnoreCase(e.getValue()) : actual.equals(e.getValue());
            if (!matches) {
                return false;
            }
        }
        return true;
    }

    private static XMLInputFactory buildXmlInputFactory() {
        XMLInputFactory factory = XMLInputFactory.newInstance();
        // Harden against XXE — this parses attacker-reachable request bodies.
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty("javax.xml.stream.isSupportingExternalEntities", false);
        return factory;
    }

    /** Streams `body` looking for the first leaf element named `fieldName`,
     * matching only its local (namespace-stripped) name — mirrors the
     * generator's local-name-based selection (_xml_leaf_values). Returns
     * null if not found or the body isn't well-formed XML. Never builds a
     * DOM: stops reading as soon as the target element closes. */
    private static String extractXmlField(String body, String fieldName) {
        if (body == null || body.isEmpty()) {
            return null;
        }
        try {
            XMLStreamReader reader = XML_INPUT_FACTORY.createXMLStreamReader(new StringReader(body));
            try {
                boolean insideTarget = false;
                StringBuilder text = null;
                while (reader.hasNext()) {
                    int event = reader.next();
                    if (event == XMLStreamConstants.START_ELEMENT) {
                        if (reader.getLocalName().equals(fieldName)) {
                            insideTarget = true;
                            text = new StringBuilder();
                        }
                    } else if (event == XMLStreamConstants.CHARACTERS && insideTarget) {
                        text.append(reader.getText());
                    } else if (event == XMLStreamConstants.END_ELEMENT && insideTarget
                            && reader.getLocalName().equals(fieldName)) {
                        return text.toString().trim();
                    }
                }
            } finally {
                reader.close();
            }
        } catch (Exception e) {
            log.debug("DynamicLookupRequestFilter: could not parse XML body for discriminator extraction", e);
        }
        return null;
    }

    /** Streams `body` looking for a top-level JSON field named `fieldName`
     * (matches generator's _json_leaf_values, which only ever selects
     * top-level scalar fields as discriminators). Never materialises a
     * full tree: skips every other field's value without parsing it. */
    private static String extractJsonField(String body, String fieldName) {
        if (body == null || body.isEmpty()) {
            return null;
        }
        try (JsonParser parser = JSON_FACTORY.createParser(body)) {
            if (parser.nextToken() != JsonToken.START_OBJECT) {
                return null;
            }
            while (parser.nextToken() == JsonToken.FIELD_NAME) {
                String field = parser.getCurrentName();
                parser.nextToken();
                if (field.equals(fieldName)) {
                    return parser.getValueAsString();
                }
                parser.skipChildren(); // no-op for scalars; skips nested objects/arrays
            }
        } catch (Exception e) {
            log.debug("DynamicLookupRequestFilter: could not parse JSON body for discriminator extraction", e);
        }
        return null;
    }

    // ── route data ───────────────────────────────────────────────────────

    private static final class LookupRoute {
        final String method;
        final String urlPath;      // set for exact-URL, body-discriminated routes
        final Pattern urlPattern;  // set for URL-pattern, path-discriminated routes
        final Map<String, String> requiredHeaders;
        final String discriminatorType; // "xpath" | "json" | "url-segment"
        final String discriminatorField; // null for "url-segment" — the value comes from the URL match instead
        final Map<String, CannedResponse> entries;

        private LookupRoute(String method, String urlPath, Pattern urlPattern, Map<String, String> requiredHeaders,
                             String discriminatorType, String discriminatorField,
                             Map<String, CannedResponse> entries) {
            this.method = method;
            this.urlPath = urlPath;
            this.urlPattern = urlPattern;
            this.requiredHeaders = requiredHeaders;
            this.discriminatorType = discriminatorType;
            this.discriminatorField = discriminatorField;
            this.entries = entries;
        }

        /** Body-based discriminator extraction — never called for a
         * "url-segment" route, whose discriminator comes from the URL
         * pattern's capture group instead (see filter()). */
        String extractBodyDiscriminator(String body) {
            if (discriminatorField == null) {
                return null;
            }
            return "xpath".equals(discriminatorType)
                    ? extractXmlField(body, discriminatorField)
                    : extractJsonField(body, discriminatorField);
        }

        static LookupRoute fromJson(JsonNode root) {
            String method = root.path("method").asText("GET");
            String urlPath = root.hasNonNull("urlPath") ? root.get("urlPath").asText() : null;
            String urlPatternText = root.hasNonNull("urlPattern") ? root.get("urlPattern").asText() : null;
            Pattern urlPattern = urlPatternText != null ? Pattern.compile(urlPatternText) : null;
            String discriminatorType = root.hasNonNull("discriminatorType")
                    ? root.get("discriminatorType").asText() : null;
            String discriminatorField = root.hasNonNull("discriminatorField")
                    ? root.get("discriminatorField").asText() : null;

            Map<String, String> requiredHeaders = new HashMap<>();
            JsonNode headersNode = root.path("requiredHeaders");
            for (Iterator<String> it = headersNode.fieldNames(); it.hasNext(); ) {
                String name = it.next();
                requiredHeaders.put(name, headersNode.get(name).asText());
            }

            Map<String, CannedResponse> entries = new HashMap<>();
            for (JsonNode entryNode : root.path("entries")) {
                String key = entryNode.path("key").asText(null);
                if (key == null) {
                    continue;
                }
                int status = entryNode.path("status").asInt(200);
                Map<String, String> headers = new HashMap<>();
                JsonNode headersEntry = entryNode.path("headers");
                for (Iterator<String> it = headersEntry.fieldNames(); it.hasNext(); ) {
                    String name = it.next();
                    headers.put(name, headersEntry.get(name).asText());
                }
                String body = entryNode.hasNonNull("body") ? entryNode.get("body").asText() : null;
                entries.put(key, new CannedResponse(status, Collections.unmodifiableMap(headers), body));
            }

            return new LookupRoute(
                    method,
                    urlPath,
                    urlPattern,
                    Collections.unmodifiableMap(requiredHeaders),
                    discriminatorType,
                    discriminatorField,
                    Collections.unmodifiableMap(entries));
        }
    }

    private record CannedResponse(int status, Map<String, String> headers, String body) {}
}
