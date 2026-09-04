#!/usr/bin/env bash
# Simple script to set up the Mockingbird stub on a RHEL8 EC2 box.
# Downloads Java and the jar from S3, installs Java, and starts the stub.
#
# Run as root:  sudo ./deploy-stub-ec2.sh

set -e

# ---- change these to match your S3 files ----
BUCKET="lre-poc-bucket"
JAVA_FILE="amazon-corretto-21.0.10.7.1-linux-x64.tar.gz"
JAR_FILE="app.jar"
REGION="eu-west-2"

# ---- where things get installed ----
JAVA_DIR="/opt/corretto-21"
APP_DIR="/opt/mockingbird-stub"

echo "Step 1: Downloading Java from S3..."
mkdir -p "$APP_DIR"
aws s3 cp "s3://$BUCKET/$JAVA_FILE" /tmp/java.tar.gz --region "$REGION"

echo "Step 2: Installing Java to $JAVA_DIR..."
mkdir -p "$JAVA_DIR"
tar -xzf /tmp/java.tar.gz -C "$JAVA_DIR" --strip-components=1
"$JAVA_DIR/bin/java" -version

echo "Step 3: Setting JAVA_HOME so it's available in every terminal..."
echo "export JAVA_HOME=$JAVA_DIR" > /etc/profile.d/java.sh
echo "export PATH=\$JAVA_HOME/bin:\$PATH" >> /etc/profile.d/java.sh

echo "Step 4: Downloading the stub jar from S3..."
aws s3 cp "s3://$BUCKET/$JAR_FILE" "$APP_DIR/app.jar" --region "$REGION"

echo "Step 5: Creating a service so the stub starts automatically and restarts if it crashes..."
cat > /etc/systemd/system/mockingbird-stub.service <<EOF
[Unit]
Description=Mockingbird Stub Engine
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$JAVA_DIR/bin/java -Xmx24g -jar $APP_DIR/app.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "Step 6: Starting the stub..."
systemctl daemon-reload
systemctl enable mockingbird-stub
systemctl restart mockingbird-stub

echo ""
echo "Done. Check it worked with:"
echo "  curl http://localhost:8081/actuator/health"
echo ""
echo "To see logs:      journalctl -u mockingbird-stub -f"
echo "To stop:          systemctl stop mockingbird-stub"
echo "To redeploy a new jar: upload the new app.jar to S3, then run this script again."
