# rtsp-monitor
---

## Docker Setup and Usage

1. **Pull the Docker image**:

   ```bash
   docker pull digodigo/projects-rtsp-monitor:latest
   ```

2. **Run the Docker container**:

   ```bash
   docker run -d \
       -p 5000:5000 \
       --name camera-test-app \
       digodigo/projects-rtsp-monitor:latest
   ```

   - **`-p 5000:5000`**: Exposes container’s port 5000 to the host on the same port.
   - **`-d`**: Runs the container in detached mode (in the background).
   - **`--name camera-test-app`**: Names the container for easy reference (optional).

3. **Access the Application**:

   Open your browser and go to `http://localhost:5000` (or replace `localhost` with the host IP if running on a remote server).  
   You will see a simple interface for uploading your CSV file, specifying (optionally) a maximum number of streams to test, and generating reports.

---

## Using the Application

1. **Upload the CSV File**:  
   On the main page, select the CSV file that contains the camera information. (See “CSV Format” below for more details.)

2. **Optional: Max Streams**:  
   If you want to limit how many streams are tested (e.g., 10), enter the number in the “Max Streams” field.

3. **Generate Reports**:  
   - After processing, the app displays the status for each camera (valid or not valid) along with any error messages.
   - You can download a text file report (`client_report.txt`) and a PDF report (`client_report.pdf`) to review detailed information and screenshots.

---

## CSV Format

- **Required Columns**:
  - **Camera Name** (or **Client Camera Name**)  
  - **URL** (or **RTSP URL**)

Below is an example of a minimal CSV:

```csv
Camera Name,RTSP URL
Front Door,rtsp://192.168.1.10:554/stream
Office,rtsp://192.168.1.20:554/stream
```

If your CSV uses different column headers, the app will attempt to fall back on the alternative column names shown in the code (e.g., `URL` or `RTSP URL`; `Camera Name` or `Client Camera Name`).  

**Note**: If neither column for camera name nor URL is found, the app will label the camera as “Unnamed_Camera” and show an error.

---
