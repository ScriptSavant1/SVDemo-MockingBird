package com.mockingbird.stubs;

import com.github.tomakehurst.wiremock.client.ResponseDefinitionBuilder;
import com.github.tomakehurst.wiremock.extension.requestfilter.RequestFilterAction;
import com.github.tomakehurst.wiremock.extension.requestfilter.StubRequestFilterV2;
import com.github.tomakehurst.wiremock.http.Request;
import com.github.tomakehurst.wiremock.http.ResponseDefinition;
import com.github.tomakehurst.wiremock.stubbing.ServeEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.w3c.dom.Document;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.StringReader;

/**
 * Validates the WS-Security UsernameToken on inbound SOAP requests — inside
 * WireMock's own request pipeline, where it can actually see and reject real
 * stub traffic.
 *
 * This replaces an earlier Spring-WS EndpointInterceptor-based approach
 * (WsSecurityConfig.java, now deleted) that looked correct but never fired:
 * SOAP stub traffic is served entirely by WireMock's own embedded server
 * (port 8080), a completely separate HTTP stack from Spring-WS's dispatcher
 * (port 8081, used only for WSDL/actuator). An interceptor registered with
 * Spring-WS never saw stub calls at all. Verified directly: with the old
 * approach "enabled", a SOAP request with zero WS-Security header still got
 * a normal 200 from the stub. This filter is registered straight into
 * WireMockConfig's WireMockConfiguration.extensions(...), so it runs on the
 * same request path stub traffic actually takes.
 *
 * Scope: validates a plain-text UsernameToken (Username + Password) against
 * the single username/password configured for this deployment
 * (mockingbird.soap.ws-security.username / .password). Requests that don't
 * look like SOAP (no SOAPAction header and no SOAP envelope in the body) are
 * left untouched — a combined stub serving both REST and SOAP endpoints
 * shouldn't have its REST traffic rejected by a SOAP-only check. PasswordDigest
 * (nonce+timestamp hashing) isn't implemented; this mirrors the plain-text-only
 * scope the previous SimplePasswordValidationCallbackHandler-based approach had.
 */
public class WsSecurityRequestFilter implements StubRequestFilterV2 {

    private static final Logger log = LoggerFactory.getLogger(WsSecurityRequestFilter.class);

    // The WS-Security UsernameToken profile namespace — this is what actually
    // identifies the elements below, not any particular prefix. Real captures
    // use varying prefixes (NS1:, wsse:, ...); namespace-aware parsing handles
    // all of them uniformly.
    private static final String WSSE_NS =
            "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd";
    private static final String SOAP_ENVELOPE_NS = "http://schemas.xmlsoap.org/soap/envelope/";

    private final String expectedUsername;
    private final String expectedPassword;

    public WsSecurityRequestFilter(String expectedUsername, String expectedPassword) {
        this.expectedUsername = expectedUsername;
        this.expectedPassword = expectedPassword == null ? "" : expectedPassword;
    }

    @Override
    public RequestFilterAction filter(Request request, ServeEvent serveEvent) {
        if (!looksLikeSoap(request)) {
            return RequestFilterAction.continueWith(request);
        }

        String body = request.getBodyAsString();
        UsernameToken token;
        try {
            token = extractUsernameToken(body);
        } catch (Exception e) {
            log.warn("WS-Security: could not parse SOAP body as XML — rejecting. {}", e.getMessage());
            return reject("Malformed SOAP request — could not parse XML body");
        }

        if (token == null) {
            return reject("No WS-Security UsernameToken present in request");
        }
        if (!expectedUsername.equals(token.username) || !expectedPassword.equals(token.password)) {
            log.warn("WS-Security: rejected request with username '{}'", token.username);
            return reject("WS-Security authentication failed");
        }

        return RequestFilterAction.continueWith(request);
    }

    private boolean looksLikeSoap(Request request) {
        if (request.getHeader("SOAPAction") != null) {
            return true;
        }
        String contentType = request.getHeader("Content-Type");
        if (contentType != null
                && (contentType.contains("xml") || contentType.contains("soap"))) {
            return true;
        }
        String body = request.getBodyAsString();
        return body != null && body.contains("Envelope");
    }

    private RequestFilterAction reject(String reason) {
        String fault =
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                        + "<soapenv:Envelope xmlns:soapenv=\"" + SOAP_ENVELOPE_NS + "\">"
                        + "<soapenv:Body><soapenv:Fault>"
                        + "<faultcode>soapenv:Client</faultcode>"
                        + "<faultstring>" + escapeXml(reason) + "</faultstring>"
                        + "</soapenv:Fault></soapenv:Body></soapenv:Envelope>";
        ResponseDefinition response =
                new ResponseDefinitionBuilder()
                        .withStatus(500) // SOAP 1.1 convention for a server-side Fault
                        .withHeader("Content-Type", "text/xml;charset=utf-8")
                        .withBody(fault)
                        .build();
        return RequestFilterAction.stopWith(response);
    }

    private UsernameToken extractUsernameToken(String soapXml) throws Exception {
        if (soapXml == null || soapXml.isBlank()) {
            return null;
        }
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        // Harden against XXE — this parses attacker-reachable request bodies.
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        Document doc = builder.parse(new InputSource(new StringReader(soapXml)));

        NodeList usernames = doc.getElementsByTagNameNS(WSSE_NS, "Username");
        if (usernames.getLength() == 0) {
            return null;
        }
        NodeList passwords = doc.getElementsByTagNameNS(WSSE_NS, "Password");
        String username = usernames.item(0).getTextContent();
        String password = passwords.getLength() > 0 ? passwords.item(0).getTextContent() : "";
        return new UsernameToken(username, password);
    }

    private static String escapeXml(String s) {
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&apos;");
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
        return "ws-security-username-token-filter";
    }

    private record UsernameToken(String username, String password) {}
}
