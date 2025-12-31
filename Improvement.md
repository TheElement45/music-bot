# **🚀 Architecture & Feature Improvements**

This document outlines the roadmap for the bot's evolution, focusing on stability, user experience, and modern Discord features.

## **1. Core System Improvements**

### **� Slash Command Migration (High Priority)**

- **Current State:** The bot uses legacy prefix commands (`-play`).
- **Problem:** Discord is moving towards slash commands as the primary interaction method. Some features (like auto-complete) are only available via slash commands.
- **Recommendation:** Migrate all commands to `app_commands`. This will improve discoverability and allow for features like song name autocomplete in the `/play` command.

### **👤 Advanced Member Resolution**

- **Current State:** Requester information is persisted as an ID in Redis.
- **Problem:** If the Member object isn't in the cache when the bot restarts, it shows `<@ID>` instead of a mention/name.
- **Recommendation:** Implement a background resolver that attempts to fetch Member objects for persisted IDs to restore full profile information in embeds.

### **📡 Handling Large Playlists (Phase 2)**

- **Current State:** Basic background loading implemented.
- **Improvement:** Add a "Playlist Loading" progress message that updates as more songs are loaded, and allow privileged users to "Cancel" the background task.

## **2. User Experience & Polish**

### **� Interactive Search UI**

- **Current State:** `-play <query>` automatically picks the first result.
- **Improvement:** When searching (not using a direct URL), display the top 5 results with Buttons or a Select Menu for the user to pick their desired track.

### **🎵 Audio Filter UI**

- **Current State:** Filters applied via text command.
- **Improvement:** Add a button to the "Now Playing" message that opens a Modal or Select Menu to toggle audio filters without typing.

## **3. Infrastructure**

### **📊 Dashboard & Metrics**

- **Improvement:** Export bot statistics (active users, popular songs, memory usage) to a Prometheus-compatible endpoint or a simple web dashboard.
