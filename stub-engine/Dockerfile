# Java 21 base image (from GitLab Container Registry)
# Accessible from both GitLab CI AND AWS EC2 (public HTTPS endpoint)
FROM registry.gitlab.internal/your-group/engineeringartifacts/engineeringcomponents/executors/build/java/java-21.0.7_6-ubi9-9.6-1751286687:latest AS builder

WORKDIR /build

# Maven settings for Artifactory (only accessible from within the corporate network / GitLab CI)
COPY settings.xml /root/.m2/settings.xml

# Download dependencies (cached layer — only re-runs when pom.xml changes)
COPY pom.xml .
RUN mvn dependency:go-offline -B -q

# Build the fat JAR
COPY src/ src/
RUN mvn package -B -DskipTests -q

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM registry.gitlab.internal/your-group/engineeringartifacts/engineeringcomponents/executors/build/java/java-21.0.7_6-ubi9-9.6-1751286687:latest

WORKDIR /app

# AppDynamics Java agent (injected via volume in EC2 compose file, not baked in)
# ENV JAVA_TOOL_OPTIONS="-javaagent:/opt/appdynamics/javaagent.jar"

# JVM tuning for 10K+ TPS on c6i.2xlarge (8 vCPU, 16 GB)
ENV JAVA_OPTS="-Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10 -XX:+UseStringDeduplication"

COPY --from=builder /build/target/stub-engine-*.jar app.jar

# WireMock mappings directory — populated at container startup via Admin API or volume
RUN mkdir -p /app/mappings /app/__files

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
