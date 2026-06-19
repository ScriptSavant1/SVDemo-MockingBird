package com.mockingbird.stubs.mq;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.stereotype.Component;

import jakarta.jms.ConnectionFactory;
import java.util.Map;

/**
 * Dynamically registers one JMS listener per CONSUMER_REPLY stub at startup.
 *
 * Uses DefaultMessageListenerContainer so the queue name and response config
 * can be loaded at runtime from stubs.json rather than baked in as @JmsListener
 * annotations at compile time.
 */
@Component
public class MQStubConsumer {

    private static final Logger log = LoggerFactory.getLogger(MQStubConsumer.class);

    @Autowired
    private ConnectionFactory connectionFactory;

    @Autowired
    private JmsTemplate jmsTemplate;

    @Autowired
    private StubRegistry stubRegistry;

    @EventListener(ApplicationReadyEvent.class)
    public void registerConsumers() {
        for (StubDefinition stub : stubRegistry.getConsumerStubs()) {
            if (stub.consumeQueue() == null || stub.consumeQueue().isBlank()) {
                log.warn("Stub '{}' has no consumeQueue — skipping", stub.name());
                continue;
            }
            registerListener(stub);
            log.info("Registered consumer stub '{}' on queue '{}'", stub.name(), stub.consumeQueue());
        }
    }

    private void registerListener(StubDefinition stub) {
        DefaultMessageListenerContainer container = new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName(stub.consumeQueue());
        container.setSessionAcknowledgeModeName("AUTO_ACKNOWLEDGE");

        container.setMessageListener((MessageListener) message -> {
            log.debug("Stub '{}' received message on queue '{}'", stub.name(), stub.consumeQueue());
            try {
                if (stub.delayMs() > 0) {
                    Thread.sleep(stub.delayMs());
                }
                if (!stub.produceQueue().isBlank()) {
                    jmsTemplate.send(stub.produceQueue(), session -> {
                        TextMessage reply = session.createTextMessage(stub.responseBody());
                        for (Map.Entry<String, String> prop : stub.responseProperties().entrySet()) {
                            reply.setStringProperty(prop.getKey(), prop.getValue());
                        }
                        return reply;
                    });
                    log.debug("Stub '{}' sent reply to queue '{}'", stub.name(), stub.produceQueue());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (JMSException e) {
                log.error("Stub '{}' failed to send reply: {}", stub.name(), e.getMessage());
            }
        });

        container.afterPropertiesSet();
        container.start();
    }
}
