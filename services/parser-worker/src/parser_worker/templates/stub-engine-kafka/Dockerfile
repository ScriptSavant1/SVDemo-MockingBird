ARG JAVA_BASE_IMAGE=eclipse-temurin:21-jdk-alpine

FROM ${JAVA_BASE_IMAGE} AS builder

WORKDIR /build

ARG ARTIFACTORY_USR
ARG ARTIFACTORY_PSWD
COPY settings.xml /root/.m2/settings.xml

# Cache dependency layer — only re-runs when pom.xml changes
COPY pom.xml .
RUN mvn dependency:go-offline -B -q

COPY src/ src/
RUN mvn package -B -DskipTests -q

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM ${JAVA_BASE_IMAGE}

WORKDIR /app

ENV JAVA_OPTS="-Xmx4g -XX:+UseG1GC -XX:MaxGCPauseMillis=50"

COPY --from=builder /build/target/{{project_id}}-stub-*.jar app.jar

EXPOSE 8080
EXPOSE 8081

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
