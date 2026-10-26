# TeleLink Health: technical architecture guide

This guide explains the system from its overall design down to requests,
transactions, workers and code entry points. It targets engineers working on the
CS5224 Team 39 prototype. Source review date: **27 October 2026**.

Tracked as RF25 in issue #312. The guide is being assembled against the current
implementation; local runtime verification and AWS deployment are separate gates.
