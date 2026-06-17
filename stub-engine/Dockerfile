# JAVA_BASE_IMAGE is set in config/local.env → passed via:
#   docker build --build-arg JAVA_BASE_IMAGE=<your-registry>/java:21 .
# OR via GitLab CI (read from $JAVA_BASE_IMAGE CI variable).
# Default falls back to the public eclipse-temurin image for local development.
ARG JAVA_BASE_IMAGE=eclipse-temurin:21-jre-alpine

FROM ${JAVA_BASE_IMAGE} AS builder

WORKDIR /build

# Maven settings point to Artifactory via ${env.ARTIFACTORY_MAVEN_URL}
# ARTIFACTORY_USR and ARTIFACTORY_PSWD are passed as build args from CI (Vault)
ARG ARTIFACTORY_USR
ARG ARTIFACTORY_PSWD
COPY settings.xml /root/.m2/settings.xml

# Cache dependency layer — only re-runs when pom.xml changes
COPY pom.xml .
RUN mvn dependency:go-offline -B -q

# Build the fat JAR
COPY src/ src/
RUN mvn package -B -DskipTests -q

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM ${JAVA_BASE_IMAGE}

WORKDIR /app

# JVM tuning for 10K+ TPS on c6i.2xlarge (8 vCPU, 16 GB)
ENV JAVA_OPTS="-Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10 -XX:+UseStringDeduplication"

COPY --from=builder /build/target/stub-engine-*.jar app.jar

RUN mkdir -p /app/mappings /app/__files

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
