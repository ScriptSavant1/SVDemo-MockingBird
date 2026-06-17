package com.natwest.mockingbird.stubs;

import org.apache.wss4j.dom.handler.WSHandlerConstants;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;
import org.springframework.ws.soap.security.wss4j2.callback.SimplePasswordValidationCallbackHandler;

import java.util.Properties;

/**
 * WS-Security UsernameToken validation for SOAP stubs.
 *
 * Activated only when mockingbird.soap.ws-security.enabled=true (env: SOAP_WS_SECURITY_ENABLED).
 * Credentials are injected by Spring Vault at container startup — never hardcoded.
 *
 * Vault path: mockingbird/stubs/{STUB_PROJECT_ID}/soap-ws-security
 *   username: <value>
 *   password: <value>
 *
 * When enabled, all inbound SOAP requests must carry a valid WS-Security
 * UsernameToken header. Requests without a valid token receive a SOAP Fault.
 * Stub responses are never signed (securement is no-op).
 */
@Configuration
@ConditionalOnProperty(
    name  = "mockingbird.soap.ws-security.enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class WsSecurityConfig {

    // Credentials are resolved by Spring Vault bootstrap — values come from Vault,
    // never from environment variables or application.yml directly.
    @Value("${mockingbird.soap.ws-security.username}")
    private String username;

    @Value("${mockingbird.soap.ws-security.password}")
    private String password;

    @Bean
    public EndpointInterceptor wsSecurityInterceptor() {
        Wss4jSecurityInterceptor interceptor = new Wss4jSecurityInterceptor();

        // Validate the UsernameToken present in the WS-Security SOAP header
        interceptor.setValidationActions(WSHandlerConstants.USERNAME_TOKEN);

        Properties users = new Properties();
        users.setProperty(username, password != null ? password : "");

        SimplePasswordValidationCallbackHandler callbackHandler =
                new SimplePasswordValidationCallbackHandler();
        callbackHandler.setUsersMap(users);
        interceptor.setValidationCallbackHandler(callbackHandler);

        // Stub responses are plain — no signing or encryption on outbound messages
        interceptor.setSecurementActions(WSHandlerConstants.NO_SECURITY);

        return interceptor;
    }
}
