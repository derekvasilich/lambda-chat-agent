#!/bin/bash
set -e # Stop on any error

# 1. Configuration
FUNCTION_NAME="chat-agent"
PYTHON_VERSION="3.11"
BUILD_DIR="dist"
ZIP_FILE="deployment_package.zip"

echo "🚀 Starting automated build for $FUNCTION_NAME..."

# 2. Cleanup previous builds
rm -rf $BUILD_DIR $ZIP_FILE
mkdir -p $BUILD_DIR

# 3. Export dependencies using uv (No hashes, no dev tools)
echo "📦 Exporting dependencies..."
uv export --format requirements-txt --no-hashes --no-dev --no-emit-project > requirements.txt

# 4. Install dependencies for Linux (Critical for Mac users)
# We use --only-binary=:all: to ensure we get Linux-compatible wheels
echo "📥 Installing dependencies for Linux..."
pip install \
    --platform manylinux2014_x86_64 \
    --target $BUILD_DIR \
    --implementation cp \
    --python-version $PYTHON_VERSION \
    --only-binary=:all: \
    --upgrade \
    -r requirements.txt

# 5. Copy application code and other important deps
echo "📂 Copying app code..."
cp -r app $BUILD_DIR/
cp -r migrations $BUILD_DIR/
cp -r global-bundle.pem $BUILD_DIR/
cp -r alembic.ini $BUILD_DIR/
cp -r migrate.py $BUILD_DIR/

# 6. Create ZIP (from inside the dist folder)
echo "🗜️ Creating deployment package..."
cd $BUILD_DIR
zip -r ../$ZIP_FILE . > /dev/null
cd ..

# 7. Update Lambda Code
echo "☁️ Uploading to AWS Lambda..."
aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb://$ZIP_FILE

echo "✅ Deployment complete!"