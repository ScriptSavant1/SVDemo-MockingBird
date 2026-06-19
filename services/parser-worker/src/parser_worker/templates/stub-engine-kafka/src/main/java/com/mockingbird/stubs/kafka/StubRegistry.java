package com.mockingbird.stubs.kafka;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.io.InputStream;
import java.util.*;

/**
 * Loads stub definitions from stubs.json (baked into the JAR at build time).
 * Called once at startup; stubs are immutable for the lifetime of the process.
 */
@Component
public class StubRegistry {

    private final List<StubDefinition> stubs;

    public StubRegistry() throws Exception {
        InputStream is = getClass().getResourceAsStream("/stubs.json");
        if (is == null) {
            this.stubs = List.of();
            return;
        }
        ObjectMapper mapper = new ObjectMapper();
        JsonNode root = mapper.readTree(is);
        List<StubDefinition> loaded = new ArrayList<>();

        for (JsonNode node : root.path("stubs")) {
            Map<String, String> headers = new LinkedHashMap<>();
            node.path("responseHeaders").fields()
                    .forEachRemaining(e -> headers.put(e.getKey(), e.getValue().asText()));

            loaded.add(new StubDefinition(
                    node.path("name").asText(),
                    node.path("type").asText("CONSUMER_REPLY"),
                    node.path("consumeTopic").asText(""),
                    node.path("produceTopic").asText(""),
                    node.path("consumerGroup").asText("mockingbird-stub-group"),
                    node.path("responseBody").asText("{}"),
                    Collections.unmodifiableMap(headers),
                    node.path("delayMs").asInt(0)
            ));
        }
        this.stubs = Collections.unmodifiableList(loaded);
    }

    public List<StubDefinition> getAll() {
        return stubs;
    }

    public List<StubDefinition> getConsumerStubs() {
        return stubs.stream().filter(StubDefinition::isConsumerReply).toList();
    }

    public List<StubDefinition> getProducerStubs() {
        return stubs.stream().filter(StubDefinition::isProducer).toList();
    }

    public Optional<StubDefinition> findByName(String name) {
        return stubs.stream().filter(s -> s.name().equals(name)).findFirst();
    }
}
