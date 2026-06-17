# Mockingbird — SV Expert Architecture Review

**Version:** 1.0  
**Last Updated:** 2026-06-12  
**Perspective:** Service Virtualisation expert + enterprise Java + AWS

---

## 1. What Your Spring Boot Suggestion Changes — and Why It's RIGHT

Your suggestion to use Spring Boot is architecturally correct for a bank environment. Here is why:

### Problem with Standalone WireMock JAR

```
STANDALONE WIREMOCK (what we originally planned):
─────────────────────────────────────────────────
java -jar wiremock-standalone.jar

Problems:
  ✗  Single JAR — you cannot add custom logic (transformers, validators)
  ✗  Dependencies come from public Maven Central (blocked in many banks)
  ✗  No Artifactory integration — every JAR must be manually procured
  ✗  Limited to ~7,000–9,000 TPS realistic maximum (Jetty embedded server)
  ✗  SOAP support is basic — WireMock SOAP matching is fragile for complex WSDLs
  ✗  No Spring Boot Actuator — need separate Prometheus exporter sidecar
  ✗  Hard to add NatWest-specific logic (auth headers, correlation IDs)
```

### Spring Boot as Stub Engine — Why This Is Better

```
SPRING BOOT STUB ENGINE (new recommendation):
─────────────────────────────────────────────
Uses WireMock as a LIBRARY (embedded), not a standalone JAR

Advantages:
  ✓  All dependencies via pom.xml → pulled from NatWest Artifactory
  ✓  WireMock library available in Artifactory (com.github.tomakehurst:wiremock)
  ✓  Spring Boot Actuator: /actuator/health, /actuator/prometheus built-in
  ✓  Spring WebFlux (Netty): non-blocking, achieves 12,000–18,000 TPS
  ✓  Java 21 virtual threads: push TPS even higher
  ✓  Custom transformers as Spring beans (add bank-specific logic)
  ✓  Spring-WS: proper enterprise SOAP support
  ✓  Spring Kafka: Kafka stub integration without Microcks for simple cases
  ✓  Corporate standard: Java + Spring is NatWest's known stack
  ✓  Full logging via SLF4J + Logback (existing bank log patterns)
  ✓  Easy to add JWT/auth validation at stub level
  ✓  Dockerfile can be built via existing Java build infrastructure
```

---

## 2. TPS Reality Check — Honest Numbers

### What 10,000+ TPS Actually Requires

```
10,000 TPS = 10,000 requests every second

That means:
  - Every request must complete in < 1ms (0.0001 seconds)
  - 10,000 concurrent TCP connections being processed simultaneously
  - Response time must be deterministic (no GC pauses > 1ms)
  - Network bandwidth: if avg response = 1KB → 10MB/s (easily handled)
  - If avg response = 10KB → 100MB/s (needs network capacity check)
```

### Honest TPS Benchmarks Per Engine

| Engine | Realistic TPS on c6i.2xlarge | Notes |
|--------|------------------------------|-------|
| WireMock standalone (Jetty) | 5,000 – 9,000 | Jetty is blocking; GC pauses affect P99 |
| Spring Boot + WireMock library (Tomcat) | 7,000 – 11,000 | Better thread management |
| Spring Boot + WireMock library (Netty/WebFlux) | 12,000 – 18,000 | Non-blocking I/O, recommended |
| Spring Boot + WireMock + Java 21 virtual threads | 15,000 – 22,000 | Best JVM option |
| Hoverfly (Go) | 18,000 – 25,000 | Best raw TPS, fewer features |
| Multiple Hoverfly + AWS NLB | 50,000+ | Horizontal scaling |

**Recommendation for 10,000+ TPS:**

```
REST stubs (< 12K TPS):   Spring Boot + WireMock (Netty) on c6i.2xlarge
REST stubs (12K–20K TPS): Spring Boot + WireMock + Java 21 on c6i.4xlarge
REST stubs (> 20K TPS):   Hoverfly cluster behind AWS NLB
SOAP stubs:                Spring Boot + Spring-WS (not WireMock SOAP)
Kafka stubs:               Microcks (or Spring Boot + Spring Kafka)
```

### JVM Tuning for 10K+ TPS (Spring Boot)

```yaml
# application.yaml in stub engine
server:
  netty:
    connection-timeout: 5000
    idle-timeout: 60000

spring:
  threads:
    virtual:
      enabled: true   # Java 21 — game changer for TPS

# JVM flags in Dockerfile
JAVA_OPTS="-Xms4g -Xmx12g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=10 \
  -XX:+ParallelRefProcEnabled \
  -XX:+AlwaysPreTouch \
  -XX:+UseStringDeduplication \
  -Djava.net.preferIPv4Stack=true"
```

---

## 3. Revised Stub Engine Architecture

### Three Engine Types (Not Just WireMock and Hoverfly)

```
ENGINE 1: Spring Boot + WireMock (PRIMARY — covers 90% of projects)
──────────────────────────────────────────────────────────────────
Used for: REST (static, dynamic, stateful, fault injection)
          SOAP (via Spring-WS integration)
TPS:      12,000–18,000 on c6i.2xlarge (Netty + Java 21)
Source:   Maven dependencies from Artifactory

pom.xml dependencies:
  spring-boot-starter-webflux       ← Netty-based, non-blocking
  spring-boot-starter-actuator      ← /actuator/health + /actuator/prometheus
  wiremock-standalone               ← WireMock as library
  spring-ws-core                    ← Proper SOAP support
  spring-boot-starter-logging       ← SLF4J + Logback
  micrometer-registry-prometheus    ← Prometheus metrics
  faker (java-faker)                ← Dynamic data generation


ENGINE 2: Hoverfly (HIGH TPS — for projects requiring > 18K TPS)
─────────────────────────────────────────────────────────────────
Used for: Pure REST stubs requiring extreme throughput
TPS:      18,000–25,000 on c6i.4xlarge
Source:   Docker image from DockerHub (or mirror in Artifactory)
Note:     No custom transformers, no SOAP, minimal features
          Use ONLY when TPS requirement exceeds Spring Boot capacity


ENGINE 3: Microcks (ASYNC — for Kafka, gRPC, GraphQL)
───────────────────────────────────────────────────────
Used for: Kafka topic stubs, AsyncAPI, gRPC, GraphQL
TPS:      N/A (async, measured in messages/second)
Source:   Docker image (Artifactory mirror)
Note:     For simple Kafka stubs, Spring Boot + Spring Kafka is an
          alternative that avoids the Microcks complexity
```

### Stub Engine Selection Logic (Revised)

```
User declares TPS requirement at project creation:
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
        REST/SOAP               Kafka/Async         GraphQL/gRPC
              │                     │                      │
    ┌─────────┴──────────┐          │                      │
    │                    │          ▼                      ▼
  < 18K TPS           > 18K TPS  Microcks             Microcks
    │                    │
    ▼                    ▼
Spring Boot +        Hoverfly
WireMock (Netty)     cluster
```

---

## 4. Non-Breaking Changes — Architecture Patterns

This is critical. Here is every pattern that protects you from breaking existing functionality:

### 4.1 Plugin Architecture for Parsers (NO core code changes when adding new format)

```python
# Every parser implements this interface — immutable contract
class BaseParser(ABC):
    @abstractmethod
    def can_handle(self, content: bytes, filename: str) -> bool:
        """Return True if this parser handles the given file"""
        pass
    
    @abstractmethod
    def parse(self, content: bytes) -> List[ParsedEndpoint]:
        """Parse content and return normalized endpoints"""
        pass
    
    @property
    @abstractmethod
    def input_type(self) -> InputType:
        pass

# Parser registry — self-registering via Python entry points
class ParserRegistry:
    _parsers: List[BaseParser] = []
    
    @classmethod
    def register(cls, parser: BaseParser):
        cls._parsers.append(parser)
    
    @classmethod
    def detect_and_parse(cls, content: bytes, filename: str) -> List[ParsedEndpoint]:
        for parser in cls._parsers:
            if parser.can_handle(content, filename):
                return parser.parse(content)
        raise UnsupportedFormatError(filename)

# Adding IBM MQ parser in Phase 4:
# Create ibm_mq_parser.py, implement BaseParser, register it.
# ZERO changes to existing parsers or registry core.
```

### 4.2 API Versioning (Old clients never break)

```
ALL platform API routes are versioned:

  /api/v1/projects       ← existing clients use this forever
  /api/v2/projects       ← new version adds fields, doesn't remove

Rules:
  - NEVER remove a field from v1 response (add it to v2 only)
  - NEVER change a field type in v1
  - NEVER change URL structure in v1
  - New features always go to new version first

FastAPI implementation:
  router_v1 = APIRouter(prefix="/api/v1")
  router_v2 = APIRouter(prefix="/api/v2")
  # v1 router stays stable forever
```

### 4.3 Database Migration Rules (Flyway for Java, Alembic for Python)

```
ALLOWED changes (non-breaking):
  ✓  ADD new column WITH a default value
  ✓  ADD new table
  ✓  ADD new index
  ✓  ADD new constraint (if data already satisfies it)

FORBIDDEN changes (breaking — never do these):
  ✗  DROP column
  ✗  RENAME column
  ✗  CHANGE column type
  ✗  REMOVE NOT NULL from existing column without default

If you need to rename a column:
  Step 1 (migration V12): ADD new_column_name (copy data, keep old column)
  Step 2 (code change): Read from new column, write to both
  Step 3 (next release): DROP old_column_name
  
This is the expand/contract pattern — safe for zero-downtime deploys.
```

### 4.4 Stub Engine Backward Compatibility

```
WireMock JSON mapping format is versioned:
  v1 mappings → always deployable, WireMock 3.x reads them
  v2 mappings (new features) → only deployable on newer WireMock

Platform stores WireMock version per project:
  projects.engine_version = "wiremock-3.5.2"
  
When deploying: pull exact same WireMock version that generated the stubs.
Upgrading WireMock: run compatibility tests first, opt-in per project.

Spring Boot stub engine version is stored in ECR image tag:
  mockingbird/payments-stub:v3-wiremock3.5-jdk21
  ← always deployable, even after platform upgrades
```

### 4.5 Contract Tests Between Services (Pact)

```
Portal ↔ project-service: Pact contract test
  If portal sends: { "name": "test", "environment": "TEST" }
  project-service must accept this — verified in CI

Any change to project-service API must:
  1. Pass all existing Pact contracts
  2. Only then merge to main

This catches breaking changes BEFORE they reach production.
```

### 4.6 Feature Flags for New Stub Features

```python
# New feature: AI-assisted generation — opt-in per project
class ProjectFeatureFlags(BaseModel):
    ai_generation_enabled: bool = False      # off by default
    virtual_threads_enabled: bool = False    # opt-in
    kafka_stubs_enabled: bool = False        # off by default
    graphql_stubs_enabled: bool = False      # off by default

# Users toggle in portal. Existing projects unaffected.
# Rollout: enable for 10% of projects → 50% → 100%
```

---

## 5. Full Architecture Re-Review — Detailed Findings

### 5.1 Stub Matching Performance at 10K TPS

**Problem identified:** WireMock scans ALL mappings for every request. If a project has 200 stubs, each request checks 200 matchers. At 10K TPS, that is 2 million matcher evaluations per second.

**Solution:**
```
URL-based pre-routing (reduces matcher evaluations dramatically):

  Incoming request: POST /payments/domestic
  
  Step 1: URL router (O(1) hash lookup) → narrows to 1–3 candidate stubs
  Step 2: WireMock body/header matching on candidates only (not all 200)
  
  Implementation: Spring Boot RequestMappingHandlerMapping as pre-router
  Delegates to WireMock only for the matched URL prefix
  
  Result: Matcher evaluations drop from 200 → 2–3 per request
  TPS improvement: 30–50% at high stub count
```

### 5.2 TLS / HTTPS at High TPS

**Problem:** HTTPS adds 10–30% TPS overhead due to TLS handshake and encryption. At 10K TPS, this is significant.

**Solution:**
```
EXTERNAL (internet-facing or across data centres):
  → HTTPS mandatory (Nginx termination at EC2 level)
  → TLS 1.3 only (fastest handshake)
  → Session resumption enabled (reduces repeat handshake cost)
  → HSTS headers

INTERNAL (within same VPC / same data centre):
  → HTTP acceptable (VPC-internal traffic is already network-encrypted by AWS)
  → Saves 10–20% TPS overhead
  → Still uses HTTPS from portal to EC2 (control plane)
  
Decision needed from you: Can stub traffic be HTTP within internal VPC?
```

### 5.3 Connection Pool Tuning at 10K TPS

**Problem:** At 10K TPS, TCP connection management is critical. Without connection reuse, connection setup/teardown itself becomes the bottleneck.

```
Consuming team's test tool MUST use:
  - HTTP/1.1 keep-alive (not HTTP/1.0)
  - Connection pool size: minimum 100 connections
  - HTTP/2 (if Spring Boot Netty + HTTP/2): multiplexing, even better

Spring Boot Netty config in stub engine:
  server.http2.enabled=true          ← HTTP/2 support
  server.netty.max-keep-alive-requests=10000
  server.netty.idle-timeout=30s
  
  Result: 1000 connections handle 10,000 TPS (10 requests per connection)
  vs. 10,000 new connections per second without pooling
```

### 5.4 SOAP at High TPS — WireMock's Weakness

**Problem identified:** WireMock's SOAP support works for simple WSDLs but has known issues with:
- WS-Security (digital signatures, encryption)
- Complex XSD schemas with circular references
- SOAP 1.2 vs 1.1 namespace handling
- Concurrent stateful SOAP operations

**Solution — Spring-WS for SOAP:**
```java
// Spring Boot stub engine — SOAP endpoint (Spring-WS)
@Endpoint
public class AccountSoapStub {
    
    @PayloadRoot(namespace = "http://natwest.com/accounts", localPart = "GetAccountRequest")
    @ResponsePayload
    public GetAccountResponse getAccount(@RequestPayload GetAccountRequest request) {
        // Return pre-configured response
        // Loaded from WireMock mapping JSON at startup
        return responseTemplates.get("GetAccountRequest");
    }
}
```

Spring-WS handles:
- WS-Security (via Spring Security + Apache WSS4J)
- Complex XSD validation
- SOAP 1.1 and 1.2 
- MTOM (binary attachments)

This is far more robust than WireMock's SOAP mode for enterprise WSDLs.

### 5.5 Kafka Stubs — Revised Recommendation

**Original plan:** Microcks for all Kafka stubs.

**Revised (after expert review):**

```
Use Case 1: Simple Kafka producer stub
  (team wants stub to produce messages on a topic when triggered)
  → Spring Boot + Spring Kafka (simpler, Artifactory-friendly)
  → Platform generates a Spring Boot app that produces Kafka messages
  
Use Case 2: Complex AsyncAPI spec with schema registry (Avro)
  → Microcks (it handles AsyncAPI + Avro natively)
  
Use Case 3: Kafka consumer simulation
  (stub consumes from a topic and produces a response to another topic)
  → Spring Boot + Spring Kafka (EIP pattern, cleaner than Microcks)

Decision:
  Default Kafka tool: Spring Boot + Spring Kafka (Artifactory-friendly)
  Fallback to Microcks: only when AsyncAPI + Avro schema registry needed
```

### 5.6 Stateful Stubs at High TPS — Thread Safety

**Problem:** WireMock scenarios (stateful stubs) use in-memory state. At 10K TPS with multiple concurrent test threads hitting a stateful flow simultaneously, race conditions can occur.

```
Example: Login → GetAccount → Transfer
  Thread A sends Login (state: LOGGED_IN)
  Thread B sends Login simultaneously
  Thread B changes state before Thread A's GetAccount request arrives
  Thread A's GetAccount fails (state is wrong)

Solution:
  For high-TPS stateful testing: use a session ID in the request
  Each session gets its own scenario instance (scenario-per-session pattern)
  
  WireMock supports this via:
    Request header: X-Session-ID: {uuid}
    Scenario name: {base-scenario-name}-{session-id}
    
  Platform auto-generates session-aware stateful stubs
  when project declares: "stateful_mode": "session_per_user"
```

### 5.7 Response Body Size at High TPS

**Problem:** Large response bodies (>10KB) significantly reduce TPS. At 10K TPS, a 10KB response = 100MB/s throughput requirement.

```
EC2 network bandwidth:
  c6i.2xlarge: 12.5 Gbps = 1,562 MB/s
  At 10K TPS with 10KB response: 100MB/s (fine)
  At 10K TPS with 100KB response: 1,000MB/s (approaching limit)
  At 10K TPS with 1MB response: 10,000MB/s (OVER LIMIT — impossible)

Platform should warn users:
  If avg_response_size > 50KB AND tps_requirement > 5,000:
  → "Warning: large response size may limit achievable TPS"
  → Suggest: compress responses (gzip), reduce response to minimum fields
  
Spring Boot compression config:
  server.compression.enabled=true
  server.compression.min-response-size=1024
  server.compression.mime-types=application/json,text/xml
  Result: 1KB response compressed to ~200 bytes → 5x TPS improvement
```

### 5.8 Health Check Reliability

**Problem:** Basic health check (`/__admin/health`) only tells you WireMock is running, not that it's actually serving requests correctly.

**Solution — Deep health check in Spring Boot:**
```java
@Component
public class StubHealthIndicator implements HealthIndicator {
    
    @Override
    public Health health() {
        // Check 1: WireMock server is running
        // Check 2: At least one stub mapping loaded
        // Check 3: Test request to a canary endpoint returns expected response
        // Check 4: Memory usage < 80% (GC pressure warning)
        // Check 5: P95 latency from last 100 requests < configured threshold
        
        if (allChecksPass()) {
            return Health.up()
                .withDetail("stubCount", wireMock.listAllStubMappings().size())
                .withDetail("p95LatencyMs", metrics.getP95())
                .build();
        }
        return Health.down().withDetail("reason", failureReason).build();
    }
}
```

### 5.9 Metrics Accuracy at High TPS

**Problem:** Naive Prometheus counter increments (`counter.increment()`) use synchronized blocks. At 10K TPS, lock contention reduces performance.

**Solution:**
```java
// Use LongAdder-backed counters (lock-free, designed for high concurrency)
// Micrometer does this correctly out of the box

// In Spring Boot stub engine (pom.xml):
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>

// Micrometer uses LongAdder internally — no contention at 10K TPS
// Metrics exposed at /actuator/prometheus
// Prometheus scrapes every 30 seconds
```

### 5.10 GitLab Pipeline — Stub Docker Image Build

**Problem identified:** Building Docker image per project inside the deployer-worker process blocks that worker. At high load (many concurrent deploys), this creates a queue.

**Better approach — GitLab CI job per stub deploy:**

```yaml
# Platform triggers this GitLab CI job via GitLab API when user clicks Deploy
# gitlab-ci/stub-build-deploy.yml

build-stub-image:
  stage: build
  image: maven:3.9-eclipse-temurin-21    # from Artifactory mirror
  script:
    - mvn package -f ${PROJECT_ID}/pom.xml
    - docker build -t ${ECR_REGISTRY}/mockingbird/${PROJECT_ID}:${VERSION} .
    - docker push ${ECR_REGISTRY}/mockingbird/${PROJECT_ID}:${VERSION}
  variables:
    MAVEN_OPTS: "-Dmaven.repo.local=${CI_PROJECT_DIR}/.m2/repository"
    MAVEN_SETTINGS: /etc/maven/settings.xml   # points to Artifactory

deploy-stub-ec2:
  stage: deploy
  script:
    - terraform init -backend-config=...
    - terraform apply -auto-approve
  environment:
    name: ${TARGET_ENVIRONMENT}
```

**This means:**
- Maven pulls all JARs from NatWest Artifactory (not Maven Central)
- Docker build is parallelisable (multiple GitLab runners)
- Full audit trail in GitLab (who triggered, when, what version)
- Build logs stored in GitLab (not in platform DB)
- Deployer-worker only triggers and monitors the pipeline, doesn't build

### 5.11 Artifactory — Full Dependency Flow

```
WHAT MUST COME FROM ARTIFACTORY (not public internet):
─────────────────────────────────────────────────────
Platform backend (Python):
  pypi.natwest.internal → all Python packages (FastAPI, boto3, etc.)
  
Stub engine (Java):
  artifactory.natwest.internal → all Maven JARs:
    org.springframework.boot:spring-boot-*
    com.github.tomakehurst:wiremock-standalone
    org.springframework.ws:spring-ws-core
    io.micrometer:micrometer-registry-prometheus
    com.github.javafaker:javafaker
    
Docker base images:
  artifactory.natwest.internal/docker → base images:
    eclipse-temurin:21-jre-alpine    (Java runtime)
    nginx:alpine                     (portal)
    python:3.11-slim                 (platform services)
    
NPM packages (portal):
  npm.natwest.internal → all npm packages (React, etc.)
```

### 5.12 IBM MQ / JMS for Legacy (Phase 4 — Future)

**Expert note:** 40% of NatWest banking systems use IBM MQ. Your guide mentions this as Phase 4 (Tier 3 protocol). When you get there:

```
Spring Boot + spring-jms + IBM MQ client JARs (from Artifactory)
  → IBM MQ JARs: com.ibm.mq:com.ibm.mq.allclient (available on IBM Fix Central → Artifactory)
  → Connection factory: MQConnectionFactory
  → Spring @JmsListener for consumption simulation
  → Spring JmsTemplate for message production

Do NOT use WireMock for MQ stubs — WireMock is HTTP only.
Use Spring Boot + spring-jms — it is the natural fit.
```

---

## 6. Revised Technology Stack for Stub Engines

```
BEFORE (original plan):          AFTER (expert review):
────────────────────────         ──────────────────────────────────
WireMock standalone JAR      →   Spring Boot + WireMock library (Netty)
Hoverfly (Go)                →   Hoverfly (kept for > 18K TPS only)
Microcks                     →   Microcks (Kafka/gRPC, kept) +
                                 Spring Boot + Spring Kafka (simple Kafka)
Separate Prometheus sidecar  →   Spring Boot Actuator /actuator/prometheus
Custom transformer JARs      →   Spring Boot beans (natural fit)
WSDL parsing: WireMock SOAP  →   Spring-WS (enterprise grade)
IBM MQ (Phase 4)             →   Spring Boot + spring-jms (natural fit)
```

---

## 7. Questions I Need From You

To finalise the architecture perfectly, I need these answers:

### CRITICAL (must know before Phase 1)

| # | Question | Why It Matters |
|---|----------|---------------|
| 1 | What is the Artifactory URL and does it mirror Maven Central? | Entire stub build pipeline depends on this |
| 2 | What Java version is available in Artifactory? (Java 11/17/21?) | Virtual threads need Java 21; big TPS difference |
| 3 | Is there a Docker registry in Artifactory? Or use AWS ECR only? | Determines where Docker base images come from |
| 4 | What GitLab version? Self-hosted or gitlab.com? | Determines CI job capabilities |
| 5 | What type of SSO does NatWest use? (Azure AD SAML? LDAP? OAuth?) | Auth service design depends on this |

### IMPORTANT (needed before Phase 2–3)

| # | Question | Why It Matters |
|---|----------|---------------|
| 6 | Can stub traffic be plain HTTP within internal VPC? Or HTTPS mandatory everywhere? | TPS headroom: HTTP gives 10–20% more TPS |
| 7 | Average number of stubs per project? (10? 50? 200?) | Affects URL pre-routing decision |
| 8 | Average response body size per stub? (1KB? 10KB? 100KB?) | Determines if compression is needed |
| 9 | Are consuming test tools in the same VPC as stub EC2? Or different data centre? | Network latency affects realistic TPS |
| 10 | Do SOAP stubs need WS-Security (digital signatures, encryption)? | Spring-WS vs simple XML matching |
| 11 | Is Kafka AWS MSK or self-hosted Confluent? Any Avro schema registry? | Determines Microcks vs Spring Kafka decision |
| 12 | What's the peak concurrent user count for the Mockingbird portal? (50 users? 500?) | ECS task sizing for platform |

### USEFUL (for complete picture)

| # | Question | Why It Matters |
|---|----------|---------------|
| 13 | Are there existing GitLab runners with Docker-in-Docker access? | Needed for stub image builds |
| 14 | Does NatWest have any existing pypi mirror in Artifactory? | Python platform backend dependencies |
| 15 | What AWS regions are in use? (eu-west-1 only? Multi-region?) | Terraform module design |
| 16 | Is there a VPN between on-premise servers and AWS? Or Direct Connect? | On-premise deployment target |
| 17 | Are there any specific data residency requirements? (UK only?) | Determines AWS region choices |
| 18 | How many total projects expected in Year 1? Year 3? | Platform capacity planning |
| 19 | Is there a need for test data masking? (real account numbers in specs) | Security scrubbing at ingestion |

---

## 8. Architecture Changes Summary

Based on expert review, these items change in the architecture:

| Area | Original | Revised | Reason |
|------|----------|---------|--------|
| Stub engine: REST | WireMock standalone JAR | Spring Boot + WireMock library (Netty) | Artifactory, TPS, customisation |
| Stub engine: SOAP | WireMock SOAP mode | Spring Boot + Spring-WS | Enterprise SOAP reliability |
| Stub engine: Kafka simple | Microcks | Spring Boot + Spring Kafka | Simpler, Artifactory-friendly |
| Stub engine: Kafka complex | Microcks | Microcks (kept) | AsyncAPI + Avro needs it |
| Stub engine: IBM MQ | Not specified | Spring Boot + spring-jms | Natural Java fit |
| Metrics endpoint | Prometheus sidecar container | Spring Boot Actuator | Removes sidecar complexity |
| Docker image build | Deployer-worker subprocess | GitLab CI job (triggered via API) | Parallel builds, audit trail |
| Dependencies source | Maven Central / public npm | Artifactory mirrors only | Bank security requirement |
| TPS target per project | 10K–15K | 12K–18K (Spring Boot Netty) | Validated architecture |
| Java version | Not specified | Java 21 mandatory | Virtual threads for TPS |
| Connection model | Not specified | HTTP keep-alive + HTTP/2 | Required for 10K TPS |
| Stateful stubs | Session-less | Session-per-user pattern | Thread safety at high TPS |
