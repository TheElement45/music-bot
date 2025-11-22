# **🐞 Bug Report & Critical Logic Gaps**

This document outlines specific bugs, unimplemented features, and logic errors identified in the current codebase.

## **1\. Critical Logic Gaps**

### **🔴 Missing "Vote Skip" Implementation**

**Severity:** High

* **Description:** The config.py file defines ENABLE\_VOTE\_SKIP and VOTE\_SKIP\_THRESHOLD, implying the feature exists. However, the skip command in music\_cog.py directly calls vc.stop() without checking for permissions or calculating votes.  
* **Current Behavior:** Any user with access to the command can skip songs immediately, ignoring the configuration.  
* **Fix Required:** \- Implement a check in the skip command.  
  * If the user is not a DJ/Admin, add their ID to a set (self.vote\_skip\_voters).  
  * Calculate len(voters) / len(listeners).  
  * Only execute vc.stop() if the threshold is met.

### **🔴 Non-Functional "Seek" Command**

**Severity:** Medium

* **Description:** The seek command currently calculates a timestamp and sends a message saying "Seeking...", but explicitly logs that the feature is not implemented. It is a "placebo" command.  
* **Current Behavior:** The bot replies "Seeking to X..." but the audio continues playing normally without change.  
* **Fix Required:** \- The VoiceClient source cannot be "seeked" in place.  
  * You must destroy the current audio source.  
  * Re-create the FFmpegOpusAudio source, passing before\_options="-ss \<seconds\>" to FFmpeg.  
  * Restart playback with the new source.

### **🔴 Spotify Playback Failures**

**Severity:** Medium

* **Description:** utils/helpers.py allows spotify.com URLs, but standard yt-dlp cannot stream audio from Spotify due to DRM protections.  
* **Current Behavior:** Users inputting Spotify links will likely receive no audio or an error, despite the URL passing validation.  
* **Fix Required:** \- Detect Spotify URLs in play.  
  * Use the Spotify API (or scraper) to get "Artist \- Song Name".  
  * Perform a text-based search on YouTube for that query.  
  * Stream the YouTube result instead.

## **2\. Code & Logic Bugs**

### **🐛 Disconnect Race Condition**

**Location:** cogs/music\_cog.py \-\> leave command vs on\_voice\_state\_update

* **Description:** The leave command cleans up the queue and state, then calls vc.disconnect(). The disconnect() action triggers the on\_voice\_state\_update event listener, which *also* attempts to clean up the queue and state.  
* **Impact:** Redundant operations and potential logging of "Unexpected disconnect" when it was intentional.  
* **Fix:** Add a flag (e.g., self.is\_disconnecting \= True) before calling disconnect, or check if the queue is already empty/cleaned before processing the event listener.

### **🐛 Loop Button Visual State**

**Location:** cogs/music\_cog.py \-\> MusicControlView.update\_buttons

* **Description:** The logic for the loop button style is inconsistent. It sets the emoji to 🔁 for both 'Queue Loop' and 'Loop Off'.  
* **Impact:** Users cannot visually distinguish between "Looping the Queue" and "Looping Off" just by looking at the emoji.  
* **Fix:** Change the emoji for "Off" to 🚫 or ➡️, or ensure the button style (Green vs Grey) is distinct enough and explicitly handled.

### **🐛 Generic Permission Error Handling**

**Location:** cogs/music\_cog.py \-\> play

* **Description:** If the bot attempts to join a voice channel it doesn't have access to, it catches a generic Exception.  
* **Impact:** The logs show a generic connection error, and the user gets a vague "Error connecting" message.  
* **Fix:** Explicitly catch discord.errors.Forbidden and reply with "I do not have permission to join your voice channel."