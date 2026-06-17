package com.natwest.mockingbird.stubs;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.wsdl.wsdl11.SimpleWsdl11Definition;

/**
 * WSDL serving for SOAP stubs.
 *
 * Activated only when mockingbird.soap.wsdl.enabled=true (env: SOAP_WSDL_ENABLED).
 *
 * Place the project WSDL at:
 *   src/main/resources/wsdl/service.wsdl
 *
 * WireMock serves the WSDL at:
 *   http://host:8080/ws/service.wsdl
 *
 * The bean name "service" determines the WSDL URL path segment.
 * Change the bean name to change the URL (e.g. "payment" → /ws/payment.wsdl).
 */
@Configuration
@ConditionalOnProperty(
    name  = "mockingbird.soap.wsdl.enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class WsdlConfig {

    @Bean(name = "service")
    public SimpleWsdl11Definition serviceWsdl() {
        SimpleWsdl11Definition wsdl = new SimpleWsdl11Definition();
        wsdl.setWsdl(new ClassPathResource("/wsdl/service.wsdl"));
        return wsdl;
    }
}
