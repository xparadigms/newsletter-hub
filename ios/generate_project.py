#!/usr/bin/env python3
"""Writes TheBrief.xcodeproj from the files under TheBrief/.

Run it after adding or removing a source file:  python3 ios/generate_project.py
The project is plain pbxproj (objectVersion 56) so it opens in any Xcode from
15 up, and every ID is derived from a file's path, so regenerating an
unchanged tree produces an identical file.
"""
import hashlib
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = "TheBrief"
BUNDLE_ID = "com.heechangkang.thebrief"
DISPLAY_NAME = "The Brief"


def uid(*parts):
    return hashlib.md5("/".join(parts).encode()).hexdigest()[:24].upper()


def q(s):
    return s if s.replace("_", "").replace(".", "").replace("/", "").isalnum() else '"%s"' % s


sources, resources = [], []
tree = {}  # dir -> list of (name, path)
for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, APP)):
    dirnames[:] = sorted(d for d in dirnames if not d.endswith(".xcassets"))
    rel = os.path.relpath(dirpath, ROOT)
    entries = tree.setdefault(rel, [])
    for d in dirnames:
        entries.append((d, os.path.join(rel, d), "group"))
    for f in sorted(filenames):
        path = os.path.join(rel, f)
        if f.endswith(".swift"):
            sources.append(path)
            entries.append((f, path, "file"))
        elif f == "Info.plist":
            entries.append((f, path, "file"))
    for asset in sorted(os.listdir(dirpath)):
        if asset.endswith(".xcassets"):
            path = os.path.join(rel, asset)
            resources.append(path)
            entries.append((asset, path, "file"))

FILETYPES = {".swift": "sourcecode.swift", ".plist": "text.plist.xml", ".xcassets": "folder.assetcatalog"}

o = []
w = o.append
w("// !$*UTF8*$!\n{\n\tarchiveVersion = 1;\n\tclasses = {\n\t};\n\tobjectVersion = 56;\n\tobjects = {\n")

w("\n/* Begin PBXBuildFile section */\n")
for p in sources:
    w("\t\t%s /* %s in Sources */ = {isa = PBXBuildFile; fileRef = %s; };\n" % (uid("build", p), os.path.basename(p), uid("ref", p)))
for p in resources:
    w("\t\t%s /* %s in Resources */ = {isa = PBXBuildFile; fileRef = %s; };\n" % (uid("build", p), os.path.basename(p), uid("ref", p)))
w("/* End PBXBuildFile section */\n")

w("\n/* Begin PBXFileReference section */\n")
PRODUCT = uid("product")
w("\t\t%s /* %s.app */ = {isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = %s.app; sourceTree = BUILT_PRODUCTS_DIR; };\n" % (PRODUCT, APP, APP))
for rel, entries in tree.items():
    for name, path, kind in entries:
        if kind != "file":
            continue
        ext = os.path.splitext(name)[1]
        w("\t\t%s /* %s */ = {isa = PBXFileReference; lastKnownFileType = %s; path = %s; sourceTree = \"<group>\"; };\n"
          % (uid("ref", path), name, FILETYPES[ext], q(name)))
w("/* End PBXFileReference section */\n")

w("\n/* Begin PBXFrameworksBuildPhase section */\n")
w("\t\t%s /* Frameworks */ = {isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (\n\t\t\t); runOnlyForDeploymentPostprocessing = 0; };\n" % uid("frameworks"))
w("/* End PBXFrameworksBuildPhase section */\n")

w("\n/* Begin PBXGroup section */\n")
MAIN, PRODUCTS = uid("group", "main"), uid("group", "products")
w("\t\t%s = {isa = PBXGroup; children = (\n\t\t\t\t%s /* %s */,\n\t\t\t\t%s /* Products */,\n\t\t\t); sourceTree = \"<group>\"; };\n" % (MAIN, uid("group", APP), APP, PRODUCTS))
w("\t\t%s /* Products */ = {isa = PBXGroup; children = (\n\t\t\t\t%s /* %s.app */,\n\t\t\t); name = Products; sourceTree = \"<group>\"; };\n" % (PRODUCTS, PRODUCT, APP))
for rel, entries in tree.items():
    children = "".join(
        "\t\t\t\t%s /* %s */,\n" % (uid("group", path) if kind == "group" else uid("ref", path), name)
        for name, path, kind in entries)
    w("\t\t%s /* %s */ = {isa = PBXGroup; children = (\n%s\t\t\t); path = %s; sourceTree = \"<group>\"; };\n"
      % (uid("group", rel), os.path.basename(rel), children, q(os.path.basename(rel))))
w("/* End PBXGroup section */\n")

TARGET, PROJECT = uid("target"), uid("project")
SOURCES_PHASE, RESOURCES_PHASE = uid("sources"), uid("resources")
TARGET_CONFIGS, PROJECT_CONFIGS = uid("target-configs"), uid("project-configs")

w("\n/* Begin PBXNativeTarget section */\n")
w("""\t\t%s /* %s */ = {
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = %s;
\t\t\tbuildPhases = (
\t\t\t\t%s /* Sources */,
\t\t\t\t%s /* Frameworks */,
\t\t\t\t%s /* Resources */,
\t\t\t);
\t\t\tbuildRules = (
\t\t\t);
\t\t\tdependencies = (
\t\t\t);
\t\t\tname = %s;
\t\t\tproductName = %s;
\t\t\tproductReference = %s /* %s.app */;
\t\t\tproductType = "com.apple.product-type.application";
\t\t};
""" % (TARGET, APP, TARGET_CONFIGS, SOURCES_PHASE, uid("frameworks"), RESOURCES_PHASE, APP, APP, PRODUCT, APP))
w("/* End PBXNativeTarget section */\n")

w("\n/* Begin PBXProject section */\n")
w("""\t\t%s /* Project object */ = {
\t\t\tisa = PBXProject;
\t\t\tattributes = {
\t\t\t\tBuildIndependentTargetsInParallel = 1;
\t\t\t\tLastSwiftUpdateCheck = 1530;
\t\t\t\tLastUpgradeCheck = 1530;
\t\t\t\tTargetAttributes = {
\t\t\t\t\t%s = {
\t\t\t\t\t\tCreatedOnToolsVersion = 15.3;
\t\t\t\t\t};
\t\t\t\t};
\t\t\t};
\t\t\tbuildConfigurationList = %s;
\t\t\tcompatibilityVersion = "Xcode 14.0";
\t\t\tdevelopmentRegion = en;
\t\t\thasScannedForEncodings = 0;
\t\t\tknownRegions = (
\t\t\t\ten,
\t\t\t\tBase,
\t\t\t);
\t\t\tmainGroup = %s;
\t\t\tproductRefGroup = %s /* Products */;
\t\t\tprojectDirPath = "";
\t\t\tprojectRoot = "";
\t\t\ttargets = (
\t\t\t\t%s /* %s */,
\t\t\t);
\t\t};
""" % (PROJECT, TARGET, PROJECT_CONFIGS, MAIN, PRODUCTS, TARGET, APP))
w("/* End PBXProject section */\n")

w("\n/* Begin PBXResourcesBuildPhase section */\n")
w("\t\t%s /* Resources */ = {isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = (\n%s\t\t\t); runOnlyForDeploymentPostprocessing = 0; };\n"
  % (RESOURCES_PHASE, "".join("\t\t\t\t%s /* %s in Resources */,\n" % (uid("build", p), os.path.basename(p)) for p in resources)))
w("/* End PBXResourcesBuildPhase section */\n")

w("\n/* Begin PBXSourcesBuildPhase section */\n")
w("\t\t%s /* Sources */ = {isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = (\n%s\t\t\t); runOnlyForDeploymentPostprocessing = 0; };\n"
  % (SOURCES_PHASE, "".join("\t\t\t\t%s /* %s in Sources */,\n" % (uid("build", p), os.path.basename(p)) for p in sources)))
w("/* End PBXSourcesBuildPhase section */\n")

COMMON = {
    "ALWAYS_SEARCH_USER_PATHS": "NO",
    "CLANG_ENABLE_MODULES": "YES",
    "CLANG_ENABLE_OBJC_ARC": "YES",
    "COPY_PHASE_STRIP": "NO",
    "ENABLE_STRICT_OBJC_MSGSEND": "YES",
    "ENABLE_USER_SCRIPT_SANDBOXING": "YES",
    "GCC_C_LANGUAGE_STANDARD": "gnu17",
    "IPHONEOS_DEPLOYMENT_TARGET": "17.0",
    "LOCALIZATION_PREFERS_STRING_CATALOGS": "YES",
    "SDKROOT": "iphoneos",
}
PER_CONFIG = {
    "Debug": {
        "DEBUG_INFORMATION_FORMAT": "dwarf",
        "ENABLE_TESTABILITY": "YES",
        "GCC_OPTIMIZATION_LEVEL": "0",
        "ONLY_ACTIVE_ARCH": "YES",
        "SWIFT_ACTIVE_COMPILATION_CONDITIONS": '"DEBUG $(inherited)"',
        "SWIFT_OPTIMIZATION_LEVEL": '"-Onone"',
    },
    "Release": {
        "DEBUG_INFORMATION_FORMAT": '"dwarf-with-dsym"',
        "ENABLE_NS_ASSERTIONS": "NO",
        "SWIFT_COMPILATION_MODE": "wholemodule",
        "VALIDATE_PRODUCT": "YES",
    },
}
TARGET_SETTINGS = {
    "ASSETCATALOG_COMPILER_APPICON_NAME": "AppIcon",
    "ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME": "AccentColor",
    "CODE_SIGN_STYLE": "Automatic",
    "CURRENT_PROJECT_VERSION": "1",
    "DEVELOPMENT_TEAM": '""',
    "ENABLE_PREVIEWS": "YES",
    "GENERATE_INFOPLIST_FILE": "YES",
    "INFOPLIST_FILE": "%s/Info.plist" % APP,
    "INFOPLIST_KEY_CFBundleDisplayName": '"%s"' % DISPLAY_NAME,
    "INFOPLIST_KEY_LSApplicationCategoryType": '"public.app-category.news"',
    "INFOPLIST_KEY_UIApplicationSceneManifest_Generation": "YES",
    "INFOPLIST_KEY_UIApplicationSupportsIndirectInputEvents": "YES",
    "INFOPLIST_KEY_UILaunchScreen_Generation": "YES",
    "INFOPLIST_KEY_UISupportedInterfaceOrientations": "UIInterfaceOrientationPortrait",
    "LD_RUNPATH_SEARCH_PATHS": '"$(inherited) @executable_path/Frameworks"',
    "MARKETING_VERSION": "1.0",
    "PRODUCT_BUNDLE_IDENTIFIER": BUNDLE_ID,
    "PRODUCT_NAME": '"$(TARGET_NAME)"',
    "SWIFT_EMIT_LOC_STRINGS": "YES",
    "SWIFT_VERSION": "5.0",
    "TARGETED_DEVICE_FAMILY": "1",
}


def config(key, name, settings):
    body = "".join("\t\t\t\t%s = %s;\n" % (k, v) for k, v in sorted(settings.items()))
    return "\t\t%s /* %s */ = {\n\t\t\tisa = XCBuildConfiguration;\n\t\t\tbuildSettings = {\n%s\t\t\t};\n\t\t\tname = %s;\n\t\t};\n" % (
        key, name, body, name)


w("\n/* Begin XCBuildConfiguration section */\n")
for name in ("Debug", "Release"):
    w(config(uid("project-config", name), name, {**COMMON, **PER_CONFIG[name]}))
    w(config(uid("target-config", name), name, TARGET_SETTINGS))
w("/* End XCBuildConfiguration section */\n")

w("\n/* Begin XCConfigurationList section */\n")
for list_id, kind in ((PROJECT_CONFIGS, "project-config"), (TARGET_CONFIGS, "target-config")):
    w("\t\t%s = {\n\t\t\tisa = XCConfigurationList;\n\t\t\tbuildConfigurations = (\n\t\t\t\t%s /* Debug */,\n\t\t\t\t%s /* Release */,\n\t\t\t);\n\t\t\tdefaultConfigurationIsVisible = 0;\n\t\t\tdefaultConfigurationName = Release;\n\t\t};\n"
      % (list_id, uid(kind, "Debug"), uid(kind, "Release")))
w("/* End XCConfigurationList section */\n")

w("\t};\n\trootObject = %s /* Project object */;\n}\n" % PROJECT)

proj = os.path.join(ROOT, APP + ".xcodeproj")
os.makedirs(os.path.join(proj, "xcshareddata", "xcschemes"), exist_ok=True)
with open(os.path.join(proj, "project.pbxproj"), "w") as f:
    f.write("".join(o))

ref = 'BuildableIdentifier = "primary" BlueprintIdentifier = "%s" BuildableName = "%s.app" BlueprintName = "%s" ReferencedContainer = "container:%s.xcodeproj"' % (TARGET, APP, APP, APP)
ref = ref.replace('" ', '"\n               ')
scheme = """<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion = "1530" version = "1.7">
   <BuildAction parallelizeBuildables = "YES" buildImplicitDependencies = "YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting = "YES" buildForRunning = "YES" buildForProfiling = "YES" buildForArchiving = "YES" buildForAnalyzing = "YES">
            <BuildableReference
               %(ref)s>
            </BuildableReference>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction buildConfiguration = "Debug" selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv = "YES">
   </TestAction>
   <LaunchAction buildConfiguration = "Debug" selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB" launchStyle = "0" useCustomWorkingDirectory = "NO" ignoresPersistentStateOnLaunch = "NO" debugDocumentVersioning = "YES" debugServiceExtension = "internal" allowLocationSimulation = "YES">
      <BuildableProductRunnable runnableDebuggingMode = "0">
         <BuildableReference
            %(ref)s>
         </BuildableReference>
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction buildConfiguration = "Release" shouldUseLaunchSchemeArgsEnv = "YES" savedToolIdentifier = "" useCustomWorkingDirectory = "NO" debugDocumentVersioning = "YES">
   </ProfileAction>
   <AnalyzeAction buildConfiguration = "Debug">
   </AnalyzeAction>
   <ArchiveAction buildConfiguration = "Release" revealArchiveInOrganizer = "YES">
   </ArchiveAction>
</Scheme>
""" % {"ref": ref}
with open(os.path.join(proj, "xcshareddata", "xcschemes", APP + ".xcscheme"), "w") as f:
    f.write(scheme)
print("Wrote %s (%d sources, %d resources)" % (proj, len(sources), len(resources)))
