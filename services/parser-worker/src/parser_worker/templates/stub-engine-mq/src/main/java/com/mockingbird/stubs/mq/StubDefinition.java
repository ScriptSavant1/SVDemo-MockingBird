package com.mockingbird.stubs.mq;

import java.util.Map;

/**
 * Immutable definition of a single IBM MQ stub, loaded from stubs.json.
 *
 * Types:
 *   CONSUMER_REPLY — listens on consumeQueue, sends responseBody to produceQueue
 *   PRODUCER       — HTTP POST /api/stubs/{name}/trigger fires responseBody onto produceQueue
 */
public record StubDefinition(
        String name,
        String type,
        String consumeQueue,
        String produceQueue,
        String responseBody,
        Map<String, String> responseProperties,
        int delayMs
) {
    public boolean isConsumerReply() {
        return "CONSUMER_REPLY".equalsIgnoreCase(type);
    }

    public boolean isProducer() {
        return "PRODUCER".equalsIgnoreCase(type);
    }
}
