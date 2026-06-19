package com.mockingbird.stubs.mq;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * REST API for the IBM MQ stub engine.
 *
 * GET  /api/stubs              — list all registered stubs
 * POST /api/stubs/{name}/trigger — fire a PRODUCER stub immediately
 * GET  /health                 — lightweight health check
 */
@RestController
public class StubController {

    private static final Logger log = LoggerFactory.getLogger(StubController.class);

    @Autowired
    private JmsTemplate jmsTemplate;

    @Autowired
    private StubRegistry stubRegistry;

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "ok", "service", "mq-stub-engine"));
    }

    @GetMapping("/api/stubs")
    public ResponseEntity<Map<String, Object>> listStubs() {
        List<Map<String, String>> list = stubRegistry.getAll().stream()
                .map(s -> Map.of(
                        "name", s.name(),
                        "type", s.type(),
                        "consumeQueue", Optional.ofNullable(s.consumeQueue()).orElse(""),
                        "produceQueue", Optional.ofNullable(s.produceQueue()).orElse("")
                ))
                .toList();
        return ResponseEntity.ok(Map.of("stubs", list));
    }

    @PostMapping("/api/stubs/{name}/trigger")
    public ResponseEntity<Map<String, String>> trigger(@PathVariable String name) {
        Optional<StubDefinition> found = stubRegistry.findByName(name);
        if (found.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        StubDefinition stub = found.get();
        if (!stub.isProducer()) {
            return ResponseEntity.badRequest().body(
                    Map.of("error", "Stub '" + name + "' is not a producer stub (type=" + stub.type() + ")")
            );
        }
        jmsTemplate.send(stub.produceQueue(), session -> {
            TextMessage msg = session.createTextMessage(stub.responseBody());
            for (Map.Entry<String, String> prop : stub.responseProperties().entrySet()) {
                try {
                    msg.setStringProperty(prop.getKey(), prop.getValue());
                } catch (JMSException e) {
                    log.warn("Could not set property '{}' on message: {}", prop.getKey(), e.getMessage());
                }
            }
            return msg;
        });
        log.info("Triggered producer stub '{}' → queue '{}'", name, stub.produceQueue());
        return ResponseEntity.ok(Map.of(
                "status", "sent",
                "stub", name,
                "queue", stub.produceQueue()
        ));
    }
}
