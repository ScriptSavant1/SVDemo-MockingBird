package com.mockingbird.stubs.kafka;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.bind.annotation.*;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * REST API for the Kafka stub engine.
 *
 * GET  /api/stubs              — list all registered stubs
 * POST /api/stubs/{name}/trigger — fire a PRODUCER stub immediately
 * GET  /health                 — lightweight health check
 */
@RestController
public class StubController {

    private static final Logger log = LoggerFactory.getLogger(StubController.class);

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private StubRegistry stubRegistry;

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "ok", "service", "kafka-stub-engine"));
    }

    @GetMapping("/api/stubs")
    public ResponseEntity<Map<String, Object>> listStubs() {
        List<Map<String, String>> list = stubRegistry.getAll().stream()
                .map(s -> Map.of(
                        "name", s.name(),
                        "type", s.type(),
                        "consumeTopic", Optional.ofNullable(s.consumeTopic()).orElse(""),
                        "produceTopic", Optional.ofNullable(s.produceTopic()).orElse("")
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
        ProducerRecord<String, String> record =
                new ProducerRecord<>(stub.produceTopic(), stub.responseBody());
        for (Map.Entry<String, String> header : stub.responseHeaders().entrySet()) {
            record.headers().add(new RecordHeader(
                    header.getKey(), header.getValue().getBytes(StandardCharsets.UTF_8)
            ));
        }
        kafkaTemplate.send(record);
        log.info("Triggered producer stub '{}' → topic '{}'", name, stub.produceTopic());
        return ResponseEntity.ok(Map.of(
                "status", "sent",
                "stub", name,
                "topic", stub.produceTopic()
        ));
    }
}
