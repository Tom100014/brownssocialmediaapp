#!/bin/bash

# Setup Desktop Icon & Quick Launch
# Run this once to create a desktop shortcut

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_TYPE=$(uname -s)

echo "🎬 Setting up Browns Social Media App Desktop Launcher..."
echo ""

if [ "$OS_TYPE" = "Darwin" ]; then
    # macOS
    echo "📱 Setting up for macOS..."

    # Create a simple launcher app
    APPS_DIR="$HOME/Applications"
    APP_NAME="BrownsSocialMediaApp"

    mkdir -p "$APPS_DIR/$APP_NAME.app/Contents/MacOS"
    mkdir -p "$APPS_DIR/$APP_NAME.app/Contents"

    # Create the launcher script
    cat > "$APPS_DIR/$APP_NAME.app/Contents/MacOS/launcher" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"/../../../..
if [ ! -d "brownssocialmediaapp" ]; then
    echo "Browns Social Media App directory not found"
    exit 1
fi
cd brownssocialmediaapp
bash launcher.sh
EOF

    chmod +x "$APPS_DIR/$APP_NAME.app/Contents/MacOS/launcher"

    # Create Info.plist
    cat > "$APPS_DIR/$APP_NAME.app/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleName</key>
    <string>Browns Social Media App</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>
EOF

    echo "✅ Created: $APPS_DIR/$APP_NAME.app"
    echo ""
    echo "🎬 To launch:"
    echo "   1. Open Applications folder"
    echo "   2. Double-click BrownsSocialMediaApp"
    echo ""

elif [ "$OS_TYPE" = "Linux" ]; then
    # Linux
    echo "🐧 Setting up for Linux..."

    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"

    cat > "$DESKTOP_DIR/browns-social-media-app.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Browns Social Media App
Comment=AI-Powered Video Synthesis Platform
Exec=bash "$REPO_DIR/launcher.sh"
Icon=application-x-executable
Terminal=true
Categories=Development;Utility;
EOF

    chmod +x "$DESKTOP_DIR/browns-social-media-app.desktop"

    echo "✅ Created desktop shortcut"
    echo ""
    echo "🎬 To launch:"
    echo "   1. Open Applications menu"
    echo "   2. Search for 'Browns Social Media App'"
    echo "   3. Click to launch"
    echo ""

elif [ "$OS_TYPE" = "MINGW64_NT" ] || [ "$OS_TYPE" = "MSYS_NT" ]; then
    # Windows (Git Bash)
    echo "🪟 Setting up for Windows..."

    DESKTOP="$HOME/Desktop"
    BATCH_FILE="$DESKTOP/BrownsSocialMediaApp.bat"

    cat > "$BATCH_FILE" << 'EOF'
@echo off
cd /d %~dp0\..
cd brownssocialmediaapp
bash launcher.sh
pause
EOF

    echo "✅ Created: BrownsSocialMediaApp.bat on Desktop"
    echo ""
    echo "🎬 To launch:"
    echo "   Double-click BrownsSocialMediaApp.bat on your Desktop"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🚀 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Make sure .env.local is configured with your API keys"
echo "2. Click the launcher icon to start the app"
echo "3. Open http://localhost:3000 in your browser"
echo ""
echo "🎬 Happy video cloning! ✨"
