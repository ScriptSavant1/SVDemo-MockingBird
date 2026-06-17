package com.mockingbird.stubs;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.common.ClasspathFileSource;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import com.github.tomakehurst.wiremock.extension.responsetemplating.ResponseTemplateTransformer;
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

import java.util.concurrent.atomic.AtomicLong;

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

    private WireMockServer wireMockServer;

    @Override
    public void run(ApplicationArguments args) {
        int acceptors = Runtime.getRuntime().availableProcessors();
        int asyncThreads  = acceptors * 4;

        WireMockConfiguration config = WireMockConfiguration.options()
                .port(stubPort)
                // Jetty tuning for high TPS on c6i.2xlarge (8 vCPU, 16 GB)
                .jettyAcceptors(acceptors)
                .jettyAcceptQueueSize(1000)
                .asyncResponseEnabled(true)
                .asyncResponseThreads(asyncThreads)
                // Mappings baked into JAR under resources/mappings/
                .fileSource(new ClasspathFileSource("/"))
                // Disable admin API in production (re-enable by setting stub.admin-api.enabled=true)
                .disableRequestJournal();   // Saves memory — journal not needed at 10K TPS

        if (responseTemplatingEnabled) {
            config.extensions(new ResponseTemplateTransformer(true));
        }

        wireMockServer = new WireMockServer(config);
        wireMockServer.start();

        log.info("WireMock stub server started on port {} ({} acceptors, {} async threads)",
                stubPort, acceptors, asyncThreads);
        log.info("Loaded {} stub mappings", wireMockServer.listAllStubMappings().getMappings().size());
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
    }

    /** Exposed so other beans (e.g., SOAP config) can register stubs programmatically. */
    @Bean
    public WireMockServer wireMockServer() {
        return wireMockServer;
    }
}
