// ==============================================================================
// setup-layout.js - Plasma 6 macOS/Developer Hybrid Desktop Layout
// ==============================================================================
// Configures a sleek 32px top status/workspace bar and a centered 50px floating
// dock with pinned developer tools.

// Remove any existing panels to ensure clean idempotent rebuild
var existing = panels();
for (var i = 0; i < existing.length; i++) {
    existing[i].remove();
}

// 1. Top Status & Navigation Bar
var topBar = new Panel();
topBar.location = "top";
topBar.height = 32;

var kickoff = topBar.addWidget("org.kde.plasma.kickoff");
kickoff.currentConfigGroup = ["General"];
kickoff.writeConfig("icon", "start-here-kubuntu");
kickoff.writeConfig("favoritesPortedToKAstats", "true");

var pager = topBar.addWidget("org.kde.plasma.pager");
pager.currentConfigGroup = ["General"];
pager.writeConfig("displayedText", "Name");
pager.writeConfig("wrapPage", "true");

topBar.addWidget("org.kde.plasma.appmenu");

topBar.addWidget("org.kde.plasma.panelspacer");

var clock = topBar.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", "true");
clock.writeConfig("showSeconds", "false");
clock.writeConfig("dateFormat", "shortDate");

topBar.addWidget("org.kde.plasma.panelspacer");

topBar.addWidget("org.kde.plasma.systemtray");
topBar.addWidget("org.kde.plasma.showdesktop");

// 2. Bottom Centered Floating Dock
var dock = new Panel();
dock.location = "bottom";
dock.height = 50;
dock.alignment = "center";

var dockTasks = dock.addWidget("org.kde.plasma.icontasks");
dockTasks.currentConfigGroup = ["General"];
var launchers = [
    "applications:systemsettings.desktop",
    "applications:org.kde.konsole.desktop",
    "applications:org.kde.dolphin.desktop",
    "applications:chromium_chromium.desktop",
    "applications:code.desktop",
    "applications:md.obsidian.Obsidian.desktop"
];
dockTasks.writeConfig("launchers", launchers.join(","));

print("RKO macOS/developer hybrid layout initialized successfully.");
