package com.mockingbird.stubs;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import com.github.tomakehurst.wiremock.extension.Extension;

/**
 * Starts WireMock as an embedded HTTP server managed by Spring Boot.
 *
 * Port 8080: WireMock stub server (all stub traffic)
 * Port 8081: Spring Boot Actuator (/actuator/prometheus, /actuator/health)
 *
 * Mappings are loaded from classpath:/mappings/ (baked into the JAR by the generator).
 * The Admin API (POST /admin/mappings) can also add mappings at runtime.
 */
@Configuration
public class WireMockConfig implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(WireMockConfig.class);

    @Value("${stub.port:8080}")
    private int stubPort;

    @Value("${stub.response-templating.enabled:true}")
    private boolean responseTemplatingEnabled;

    // WS-Security UsernameToken validation — enforced by WsSecurityRequestFilter,
    // registered below only when enabled. See that class's javadoc for why this
    // lives here (in WireMock's own request pipeline) rather than in a Spring-WS
    // interceptor, which never sees stub traffic at all.
    @Value("${mockingbird.soap.ws-security.enabled:false}")
    private boolean wsSecurityEnabled;

    @Value("${mockingbird.soap.ws-security.username:stub-user}")
    private String wsSecurityUsername;

    @Value("${mockingbird.soap.ws-security.password:}")
    private String wsSecurityPassword;

    private WireMockServer wireMockServer;
    private Path extractedMappingsRoot;

    @Override
    public void run(ApplicationArguments args) throws IOException {
        int acceptors = Runtime.getRuntime().availableProcessors();
        int asyncThreads  = acceptors * 4;

        extractedMappingsRoot = extractMappingsToTempDir();

        WireMockConfiguration config = WireMockConfiguration.options()
                .port(stubPort)
                // Jetty tuning for high TPS on c6i.2xlarge (8 vCPU, 16 GB)
                .jettyAcceptors(acceptors)
                .jettyAcceptQueueSize(1000)
                .asynchronousResponseEnabled(true)
                .asynchronousResponseThreads(asyncThreads)
                // Point at a real filesystem directory extracted from the classpath (see
                // extractMappingsToTempDir), not a ClasspathFileSource. Two independent
                // reasons ClasspathFileSource doesn't work here:
                //  1. ClasspathFileSource resolves its root via ClassLoader.getResource(path).
                //     An empty-string root is ambiguous once there's more than one classpath
                //     entry (every jar/dir "has" ""), so it resolves to whichever entry
                //     happens to be first — not necessarily this app's own classes/mappings.
                //     A "/" root is worse: ClassLoader.getResource("/"), unlike
                //     Class.getResource("/"), does not treat a leading slash as
                //     classpath-root-relative — it returns null, silently falling back to
                //     `new File("/")`, the OS filesystem root.
                //  2. Even with a correct root, ClasspathFileSource opens it via
                //     java.util.zip.ZipFile when running from a packaged jar. Spring Boot
                //     3.2+'s executable jar layout addresses nested dependency/resource jars
                //     via a custom "nested:" URI scheme that plain ZipFile cannot open —
                //     confirmed by running the actual packaged jar this generator produces:
                //     it throws trying to parse a "nested:...jar" path as a filesystem path.
                // Extracting to a real temp directory via Spring's own resource resolver
                // (which already understands both plain classpath dirs and nested jars)
                // sidesteps both problems identically in dev and packaged-jar deployments.
                .usingFilesUnderDirectory(extractedMappingsRoot.toString())
                // Disable admin API in production (re-enable by setting stub.admin-api.enabled=true)
                .disableRequestJournal()   // Saves memory — journal not needed at 10K TPS
                // WireMock 3.x built-in Handlebars templating for {{request...}} placeholders
                // in response bodies/headers — replaces manually constructing a
                // ResponseTemplateTransformer, whose only constructor in 3.x takes
                // (TemplateEngine, boolean, FileSource, List<TemplateModelDataProviderExtension>).
                .globalTemplating(responseTemplatingEnabled);

        // Collected into one list and passed to a single extensions(...) call —
        // WireMockConfiguration's builder methods aren't guaranteed additive
        // across repeated calls, so this is the only way to register both
        // unconditionally (DynamicLookupRequestFilter) and conditionally
        // (WsSecurityRequestFilter) without risking one silently dropping
        // the other.
        List<Extension> extensions = new ArrayList<>();
        extensions.add(new DynamicLookupRequestFilter());
        if (wsSecurityEnabled) {
            extensions.add(new WsSecurityRequestFilter(wsSecurityUsername, wsSecurityPassword));
        }
        config.extensions(extensions.toArray(new Extension[0]));

        wireMockServer = new WireMockServer(config);
        wireMockServer.start();

        log.info("WireMock stub server started on port {} ({} acceptors, {} async threads)",
                stubPort, acceptors, asyncThreads);
        log.info("Loaded {} stub mappings", wireMockServer.listAllStubMappings().getMappings().size());
        if (wsSecurityEnabled) {
            log.info("WS-Security UsernameToken validation is ENABLED for SOAP requests (username: {})",
                    wsSecurityUsername);
        }
    }

    /**
     * Copy classpath:/mappings/*.json into a real temp directory (as
     * {tempDir}/mappings/*.json — WireMock expects "mappings" to be a child of the
     * root it's given, not the root itself) and return the temp directory.
     *
     * Uses Spring's PathMatchingResourcePatternResolver, which already knows how to
     * enumerate classpath resources correctly whether running exploded (mvn
     * spring-boot:run) or from inside a packaged jar (including Spring Boot 3.2+'s
     * nested-jar layout) — the exact cases where WireMock's own ClasspathFileSource
     * falls over (see the comment in run() above).
     */
    private Path extractMappingsToTempDir() throws IOException {
        Path tempRoot = Files.createTempDirectory("mockingbird-stub-mappings");
        Path mappingsDir = tempRoot.resolve("mappings");
        Files.createDirectories(mappingsDir);

        PathMatchingResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
        Resource[] resources = resolver.getResources("classpath*:mappings/*.json");
        for (Resource resource : resources) {
            String filename = resource.getFilename();
            if (filename == null) {
                continue;
            }
            try (InputStream in = resource.getInputStream()) {
                Files.copy(in, mappingsDir.resolve(filename), StandardCopyOption.REPLACE_EXISTING);
            }
        }
        log.info("Extracted {} mapping file(s) from classpath to {}", resources.length, mappingsDir);
        return tempRoot;
    }

    @Bean
    public MeterBinder wireMockMetrics() {
        return registry -> {
            AtomicLong stubCount = new AtomicLong(0);
            registry.gauge("wiremock.stubs.total", stubCount,
                    v -> wireMockServer != null
                            ? wireMockServer.listAllStubMappings().getMappings().size()
                            : 0);
            registry.gauge("wiremock.requests.matched", stubCount,
                    v -> wireMockServer != null
                            ? wireMockServer.countRequestsMatching(
                                    com.github.tomakehurst.wiremock.matching.RequestPatternBuilder
                                            .allRequests().build()).getCount()
                            : 0);
        };
    }

    @PreDestroy
    public void stop() {
        if (wireMockServer != null && wireMockServer.isRunning()) {
            wireMockServer.stop();
            log.info("WireMock stub server stopped.");
        }
        if (extractedMappingsRoot != null) {
            try (var paths = Files.walk(extractedMappingsRoot)) {
                paths.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try {
                        Files.deleteIfExists(p);
                    } catch (IOException ignored) {
                        // Best-effort cleanup — the OS temp dir gets reclaimed eventually anyway.
                    }
                });
            } catch (IOException ignored) {
                // Best-effort cleanup.
            }
        }
    }

    /** Exposed so other beans (e.g., SOAP config) can register stubs programmatically. */
    @Bean
    public WireMockServer wireMockServer() {
        return wireMockServer;
    }
}
