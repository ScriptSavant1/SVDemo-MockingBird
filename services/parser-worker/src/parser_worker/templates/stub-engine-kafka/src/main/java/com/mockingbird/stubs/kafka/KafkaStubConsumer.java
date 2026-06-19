package com.mockingbird.stubs.kafka;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * Dynamically registers one Kafka listener per CONSUMER_REPLY stub at startup.
 * Each listener consumes from the configured topic and produces a response.
 */
@Component
public class KafkaStubConsumer {

    private static final Logger log = LoggerFactory.getLogger(KafkaStubConsumer.class);

    @Autowired
    private ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory;

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private StubRegistry stubRegistry;

    @EventListener(ApplicationReadyEvent.class)
    public void registerConsumers() {
        for (StubDefinition stub : stubRegistry.getConsumerStubs()) {
            if (stub.consumeTopic() == null || stub.consumeTopic().isBlank()) {
                log.warn("Stub '{}' has no consumeTopic — skipping", stub.name());
                continue;
            }
            registerListener(stub);
            log.info("Registered consumer stub '{}' on topic '{}'", stub.name(), stub.consumeTopic());
        }
    }

    private void registerListener(StubDefinition stub) {
        ConcurrentMessageListenerContainer<String, String> container =
                kafkaListenerContainerFactory.createContainer(stub.consumeTopic());

        container.getContainerProperties().setGroupId(stub.consumerGroup());
        container.setupMessageListener((MessageListener<String, String>) record -> {
            log.debug("Stub '{}' received message on '{}'", stub.name(), record.topic());
            try {
                if (stub.delayMs() > 0) {
                    Thread.sleep(stub.delayMs());
                }
                if (!stub.produceTopic().isBlank()) {
                    ProducerRecord<String, String> response = new ProducerRecord<>(
                            stub.produceTopic(), record.key(), stub.responseBody()
                    );
                    for (Map.Entry<String, String> header : stub.responseHeaders().entrySet()) {
                        response.headers().add(new RecordHeader(
                                header.getKey(),
                                header.getValue().getBytes(StandardCharsets.UTF_8)
                        ));
                    }
                    kafkaTemplate.send(response);
                    log.debug("Stub '{}' sent response to '{}'", stub.name(), stub.produceTopic());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        container.start();
    }
}
