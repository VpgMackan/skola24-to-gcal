# Skola24 to Google Calendar Sync

This system scrapes your schedule from the Swedish school platform Skola24 and provides it as a standard iCalendar (ICS) feed. You can subscribe to this feed from Google Calendar, Apple Calendar, Outlook, or any other calendar application that supports ICS subscriptions. The feed automatically refreshes to keep your calendar up-to-date with any schedule changes.

## Features

- **Live Sync**: Fetches the latest schedule from Skola24 on-demand.
- **Configurable Cache**: Caches the schedule for a configurable duration to reduce load on Skola24's servers.
- **Supports Multiple Selection Types**: Works for classes, teachers, rooms, and personal student schedules (using personnummer).
- **Easy Discovery**: Includes command-line tools to help you find the necessary IDs for your school, class, or teacher.
- **Flexible Deployment**: Can be run directly with Python, as a Docker container, or as a systemd service.
- **Subject Colors**: Each subject gets a consistent pastel event color from a configurable gradient theme (`green`, `purple`, or `red`) for a cleaner, "cute" overview.

## How It Works

1.  **Configuration**: You provide your school's Skola24 domain, your school unit ID, and what schedule you want to see (e.g., a class name like "TE24A" or a teacher ID like "JW").
2.  **API Scraping**: The Python server uses the internal Skola24 API to fetch the schedule data for the specified selection.
3.  **ICS Generation**: The raw schedule data is converted into the standard iCalendar (.ics) format.
4.  **HTTP Server**: A lightweight web server exposes a URL (e.g., `http://localhost:8080/schedule.ics`) that serves the generated ICS file.
5.  **Calendar Subscription**: You add this URL to Google Calendar (or another calendar app) as a subscription. The calendar app will then periodically poll the URL to fetch the latest schedule.

## Setup and Usage

### Step 1: Download and Unpack

Download the `skola24-to-gcal.zip` file and unpack it to a directory on your computer or server.

### Step 2: Find Your School and Selection IDs

The system needs specific IDs for your school (`unit_guid`) and your desired schedule (`selection`). A command-line interface is provided to help you find these.

First, install the Python dependencies:

```bash
cd /path/to/skola24-to-gcal
sudo pip3 install -r requirements.txt
```

1.  **Find your Skola24 Host**: This is the domain name for your school's Skola24 portal, e.g., `it-gymnasiet.skola24.se`, `goteborg.skola24.se`.

2.  **List Schools to find your `unit_guid`**:

    ```bash
    python3 server.py list-schools --host your-host.skola24.se
    ```

    Find your school in the list and copy its `Unit GUID`.

3.  **List Classes, Teachers, or Rooms to find your `selection`**:

    *   To list classes:
        ```bash
        python3 server.py list-classes --host your-host.skola24.se --unit-guid <YOUR_UNIT_GUID>
        ```
        Find your class and note its exact name (e.g., "TE24A"). This will be your `selection` and you will use `selection_type: 0`.

    *   To list teachers:
        ```bash
        python3 server.py list-teachers --host your-host.skola24.se --unit-guid <YOUR_UNIT_GUID>
        ```
        Find your teacher and note their ID (e.g., "JW"). This will be your `selection` and you will use `selection_type: 7`.

### Step 3: Configure the Application

Create a `config.yaml` file in the same directory by running:

```bash
python3 server.py init-config
```

Now, open `config.yaml` with a text editor and fill in the values you found in Step 2.

**Example `config.yaml`:**

```yaml
skola24:
  host: "it-gymnasiet.skola24.se"
  school_name: "NTI Johanneberg"
  unit_guid: "MzMzODU1NjAtZGYyZS1mM2U2LTgzY2MtNDA0NGFjMmZjZjUw"
  selection: "TE24A" # The class name
  selection_type: 0    # 0 for class

schedule:
  weeks_ahead: 4
  weeks_behind: 1
  cache_ttl: 60 # Refresh every 60 seconds
  calendar_name: "Class TE24A Schedule"
  color_theme: "purple" # green, purple, or red

server:
  host: "0.0.0.0"
  port: 8080

logging:
  level: "INFO"
```

### Step 4: Run the Server

You can run the server in several ways.

**Option A: Directly with Python**

This is the simplest method for testing or running on your local machine.

```bash
python3 server.py serve
```

**Option B: Using Docker (Recommended)**

This method is recommended for running the service on a home server or NAS.

1.  Make sure you have Docker and `docker-compose` installed.
2.  Ensure your `config.yaml` is correctly filled out.
3.  Run the server in the background:

    ```bash
    docker-compose up -d
    ```

### Step 5: Add to Google Calendar

1.  Open Google Calendar on your computer.
2.  On the left, next to "Other calendars," click the `+` button.
3.  Select **"From URL"**.
4.  Enter the URL of your ICS feed. If you are running this on your local network, you will need the local IP address of the machine running the server (e.g., `http://192.168.1.100:8080/schedule.ics`). If you are running it on a public server, use its public IP or domain name.
5.  Click **"Add calendar"**. The calendar will appear on the left side under "Other calendars" and events will start to populate.

> **Note**: Google Calendar can take several hours to refresh external calendars. To force a refresh, you can access the feed URL with `?refresh=true` in your browser, but Google will still update on its own schedule.

> **Color support note**: The feed includes per-event `COLOR` values in ICS. Apple Calendar and several other clients usually show these. Google Calendar subscriptions may ignore per-event colors and use calendar-level color instead.

### Color Themes

Set this in `config.yaml` under `schedule`:

```yaml
schedule:
  color_theme: "green" # or "purple" / "red"
```

The server will generate a soft pastel gradient from that main color and assign shades consistently per subject.
