package com.mockingbird.stubs.kafka;

import java.util.Map;

/**
 * Immutable definition of a single Kafka stub, loaded from stubs.json.
 *
 * Types:
 *   CONSUMER_REPLY — listens on consumeTopic, sends responseBody to produceTopic
 *   PRODUCER       — HTTP POST /api/stubs/{name}/trigger fires responseBody onto produceTopic
 */
public record StubDefinition(
        String name,
        String type,
        String consumeTopic,
        String produceTopic,
        String consumerGroup,
        String responseBody,
        Map<String, String> responseHeaders,
        int delayMs
) {
    public boolean isConsumerReply() {
        return "CONSUMER_REPLY".equalsIgnoreCase(type);
    }

    public boolean isProducer() {
        return "PRODUCER".equalsIgnoreCase(type);
    }
}
