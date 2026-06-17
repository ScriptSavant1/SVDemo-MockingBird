package com.mockingbird.stubs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the Mockingbird stub engine.
 * WireMock acts as the HTTP server — Spring Boot manages lifecycle, config, and health.
 */
@SpringBootApplication
public class StubApplication {

    public static void main(String[] args) {
        SpringApplication.run(StubApplication.class, args);
    }
}
