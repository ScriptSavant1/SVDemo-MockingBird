package com.mockingbird.stubs.kafka;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the Mockingbird Kafka stub engine.
 * Spring Kafka manages consumer/producer lifecycle.
 * Stubs are loaded from stubs.json at startup.
 */
@SpringBootApplication
public class KafkaStubApplication {

    public static void main(String[] args) {
        SpringApplication.run(KafkaStubApplication.class, args);
    }
}
