# Two separate base images: the builder stage needs a full JDK (javac) to run
# `mvn package`; the runtime stage only needs a JRE to run the built jar. Using
# a JRE image for both (as this file previously did) breaks the build — Maven's
# compiler plugin has no `javac` to invoke on a JRE-only image.
#   docker build --build-arg JAVA_BUILD_IMAGE=<your-registry>/java:21-jdk \
#                --build-arg JAVA_RUNTIME_IMAGE=<your-registry>/java:21-jre .
# OR via GitLab CI (read from $JAVA_BUILD_IMAGE / $JAVA_RUNTIME_IMAGE CI variables).
# Defaults fall back to the public eclipse-temurin images for local development.
ARG JAVA_BUILD_IMAGE=eclipse-temurin:21-jdk-alpine
ARG JAVA_RUNTIME_IMAGE=eclipse-temurin:21-jre-alpine

FROM ${JAVA_BUILD_IMAGE} AS builder

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
FROM ${JAVA_RUNTIME_IMAGE}

WORKDIR /app

# JVM tuning for 10K+ TPS on c6i.2xlarge (8 vCPU, 16 GB)
ENV JAVA_OPTS="-Xmx12g -XX:+UseG1GC -XX:MaxGCPauseMillis=10 -XX:+UseStringDeduplication"

# Built jar is named app.jar directly (see pom.xml's <finalName>) rather than matched
# by a glob — the artifactId is a per-project slug ({{project_id}}-stub), never
# literally "stub-engine", so a `stub-engine-*.jar` glob here would match nothing
# and fail the build for every real generated project.
COPY --from=builder /build/target/app.jar app.jar

RUN mkdir -p /app/mappings /app/__files

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
