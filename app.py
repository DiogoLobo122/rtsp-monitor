import os
import cv2
import csv
import logging
import requests  # Added for HTTP error logging
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, send_from_directory, flash
from fpdf import FPDF
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for flashing messages

# Define folders and allowed extensions
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'csv'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_FOLDER, "screenshots"), exist_ok=True)

# Setup logging (logs both to file and console)
log_file = os.path.join(OUTPUT_FOLDER, "stream_log.txt")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def test_rtsp_stream(camera_name, rtsp_url, screenshot_dir, timeout=10):
    """
    Attempts to open a stream and capture a screenshot.
    Returns a tuple: (status: bool, screenshot_path: str or None, message: str)
    """
    logging.info(f"Testing camera '{camera_name}' with URL: {rtsp_url}")

    cap = cv2.VideoCapture(rtsp_url)
    start_time = datetime.now()
    success = False
    frame = None

    while (datetime.now() - start_time).seconds < timeout:
        ret, frame = cap.read()
        if ret and frame is not None:
            success = True
            break

    if success:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in (" ", "_") else "_" for c in camera_name).strip().replace(" ", "_")
        screenshot_file = os.path.join(screenshot_dir, f"{safe_name}_{timestamp}.jpg")
        cv2.imwrite(screenshot_file, frame)
        message = "Stream opened successfully and screenshot captured."
        logging.info(f"{camera_name} - {message}")
        cap.release()
        return True, screenshot_file, message
    else:
        error_message = "Failed to capture a frame from the stream."
        # Additional error logging for HTTP URLs:
        if rtsp_url.lower().startswith("http"):
            try:
                response = requests.head(rtsp_url, timeout=5)
                error_message += f" HTTP status code: {response.status_code}."
                if response.status_code == 404:
                    error_message += " Not Found (404)."
                elif response.status_code == 401:
                    error_message += " Unauthorized (401)."
            except Exception as e:
                error_message += f" Additionally, HTTP HEAD request failed with error: {e}"
        else:
            error_message += " (No additional HTTP error details available for non-HTTP URLs)"
        logging.error(f"{camera_name} - {error_message}")
        cap.release()
        return False, None, error_message

def generate_pdf_report(report_rows, output_pdf):
    """Creates a PDF report using fpdf and embeds screenshots if available."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Camera Connection Status Report", ln=True, align="C")
    pdf.ln(10)
    for row in report_rows:
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Camera Name: {row['Camera Name']}", ln=True)
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, f"Provided URL: {row['Provided URL']}", ln=True)
        pdf.cell(0, 10, f"Status: {row['Status']}", ln=True)
        pdf.cell(0, 10, f"Notes: {row['Notes']}", ln=True)
        pdf.ln(5)
        # Embed screenshot if available.
        if row.get("Screenshot"):
            try:
                current_y = pdf.get_y()
                pdf.image(row["Screenshot"], x=10, y=current_y, w=100)
                pdf.ln(80)  # Adjust spacing after the image.
            except Exception as e:
                pdf.cell(0, 10, f"Error embedding screenshot: {e}", ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)
    pdf.output(output_pdf)

def process_camera_list(input_csv, output_dir, max_streams=None):
    """Processes the CSV file and returns the report details."""
    screenshots_dir = os.path.join(output_dir, "screenshots")
    report_rows = []

    with open(input_csv, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        count = 0
        for row in reader:
            if max_streams is not None and count >= max_streams:
                break
            camera_name = row.get("Camera Name") or row.get("Client Camera Name") or "Unnamed_Camera"
            rtsp_url = row.get("RTSP URL") or row.get("URL")
            if not rtsp_url:
                message = "No URL provided."
                logging.error(f"{camera_name} - {message}")
                report_rows.append({
                    "Camera Name": camera_name,
                    "Provided URL": "",
                    "Status": "Not Valid",
                    "Notes": message,
                    "Screenshot": None
                })
                count += 1
                continue

            status, screenshot_path, message = test_rtsp_stream(camera_name, rtsp_url, screenshots_dir)
            report_rows.append({
                "Camera Name": camera_name,
                "Provided URL": rtsp_url,
                "Status": "Valid" if status else "Not Valid",
                "Notes": message if status else f"Error: {message}",
                "Screenshot": screenshot_path if status else None
            })
            count += 1

    # Generate text report
    report_file = os.path.join(output_dir, "client_report.txt")
    with open(report_file, "w", encoding="utf-8") as rep:
        rep.write("Camera Connection Status Report\n")
        rep.write("=" * 40 + "\n\n")
        for row in report_rows:
            rep.write(f"Camera Name: {row['Camera Name']}\n")
            rep.write(f"Provided URL: {row['Provided URL']}\n")
            rep.write(f"Status: {row['Status']}\n")
            rep.write(f"Notes: {row['Notes']}\n")
            rep.write("-" * 40 + "\n")
    logging.info(f"Client text report generated at: {report_file}")

    # Generate PDF report with screenshots attached
    pdf_report_file = os.path.join(output_dir, "client_report.pdf")
    generate_pdf_report(report_rows, pdf_report_file)
    logging.info(f"Client PDF report generated at: {pdf_report_file}")

    return report_rows, report_file, pdf_report_file

# Flask route: display upload form and process submitted CSV file
@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        # Check if file is part of the request
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            input_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(input_path)
            # Get the number of streams to process (if provided)
            max_streams = request.form.get("max_streams")
            try:
                max_streams = int(max_streams) if max_streams else None
            except ValueError:
                max_streams = None
            # Process the CSV file
            report_rows, text_report, pdf_report = process_camera_list(input_path, OUTPUT_FOLDER, max_streams)
            return render_template("report.html", report_rows=report_rows, pdf_report=pdf_report, text_report=text_report)
    return render_template("upload.html")

# Flask route: allow downloading reports
@app.route("/download/<path:filename>")
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

# Run the Flask app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
