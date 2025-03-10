"""
This module provides a Flask application for testing camera RTSP streams,
capturing screenshots, and generating text and PDF reports.
"""

import os
import csv
import logging
from datetime import datetime

import cv2  # pylint: disable=no-member
import requests
from flask import Flask, request, render_template, redirect, send_from_directory, flash
from fpdf import FPDF
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'

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
    """Check if the provided filename has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_http_error_details(rtsp_url):
    """
    Return HTTP error details for the given URL.

    :param rtsp_url: URL to check.
    :return: A string containing HTTP error details.
    """
    try:
        response = requests.head(rtsp_url, timeout=5)
        details = f" HTTP status code: {response.status_code}."
        if response.status_code == 404:
            details += " Not Found (404)."
        elif response.status_code == 401:
            details += " Unauthorized (401)."
        return details
    except requests.exceptions.RequestException as e:
        return f" Additionally, HTTP HEAD request failed with error: {e}"


def test_rtsp_stream(camera_name, rtsp_url, screenshot_dir, timeout=10):
    """
    Attempts to open a stream and capture a screenshot.
    Returns a tuple: (status: bool, screenshot_path: str or None, message: str)

    :param camera_name: Name of the camera.
    :param rtsp_url: URL of the RTSP stream.
    :param screenshot_dir: Directory to save the screenshot.
    :param timeout: Timeout in seconds to wait for a valid frame.
    """
    logging.info("Testing camera '%s' with URL: %s", camera_name, rtsp_url)

    cap = cv2.VideoCapture(rtsp_url)  # pylint: disable=no-member
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
        safe_name = (
            "".join(c if c.isalnum() or c in (" ", "_") else "_" for c in camera_name)
            .strip()
            .replace(" ", "_")
        )
        screenshot_file = os.path.join(screenshot_dir, f"{safe_name}_{timestamp}.jpg")
        cv2.imwrite(screenshot_file, frame)
        message = "Stream opened successfully and screenshot captured."
        logging.info("%s - %s", camera_name, message)
        cap.release()
        return True, screenshot_file, message

    error_message = "Failed to capture a frame from the stream."
    if rtsp_url.lower().startswith("http"):
        error_message += get_http_error_details(rtsp_url)
    else:
        error_message += " (No additional HTTP error details available for non-HTTP URLs)"
    logging.error("%s - %s", camera_name, error_message)
    cap.release()
    return False, None, error_message


def generate_pdf_report(report_rows, output_pdf):
    """
    Creates a PDF report using fpdf and embeds screenshots if available.

    :param report_rows: List of dictionaries with report data.
    :param output_pdf: Path to the output PDF file.
    """
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
        if row.get("Screenshot"):
            try:
                current_y = pdf.get_y()
                pdf.image(row["Screenshot"], x=10, y=current_y, w=100)
                pdf.ln(80)
            except (RuntimeError, OSError) as e:
                error_msg = f"Error embedding screenshot: {e}"
                pdf.cell(0, 10, error_msg, ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)
    pdf.output(output_pdf)


def process_csv_rows(input_csv, screenshots_dir, max_streams=None):
    """
    Processes CSV rows and returns a list of report rows.

    :param input_csv: Path to the input CSV file.
    :param screenshots_dir: Directory to save screenshots.
    :param max_streams: Maximum number of streams to process.
    :return: List of dictionaries with report data.
    """
    report_rows = []
    with open(input_csv, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        count = 0
        for row in reader:
            if max_streams is not None and count >= max_streams:
                break
            camera_name = (row.get("Camera Name")
                           or row.get("Client Camera Name")
                           or "Unnamed_Camera")
            rtsp_url = row.get("RTSP URL") or row.get("URL")
            if not rtsp_url:
                message = "No URL provided."
                logging.error("%s - %s", camera_name, message)
                report_rows.append({
                    "Camera Name": camera_name,
                    "Provided URL": "",
                    "Status": "Not Valid",
                    "Notes": message,
                    "Screenshot": None,
                })
            else:
                status, screenshot_path, msg = test_rtsp_stream(
                    camera_name, rtsp_url, screenshots_dir
                )
                report_rows.append({
                    "Camera Name": camera_name,
                    "Provided URL": rtsp_url,
                    "Status": "Valid" if status else "Not Valid",
                    "Notes": msg if status else f"Error: {msg}",
                    "Screenshot": screenshot_path if status else None,
                })
            count += 1
    return report_rows


def process_camera_list(input_csv, output_dir, max_streams=None):
    """
    Processes the CSV file and generates text and PDF reports.

    :param input_csv: Path to the input CSV file.
    :param output_dir: Directory to save output reports.
    :param max_streams: Maximum number of streams to process.
    :return: Tuple of (report_rows, text_report_path, pdf_report_path).
    """
    screenshots_dir = os.path.join(output_dir, "screenshots")
    report_rows = process_csv_rows(input_csv, screenshots_dir, max_streams)

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
    logging.info("Client text report generated at: %s", report_file)

    pdf_report_file = os.path.join(output_dir, "client_report.pdf")
    generate_pdf_report(report_rows, pdf_report_file)
    logging.info("Client PDF report generated at: %s", pdf_report_file)

    return report_rows, report_file, pdf_report_file


@app.route("/", methods=["GET", "POST"])
def upload_file():
    """Render upload form and process submitted CSV file."""
    if request.method == "POST":
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
            max_streams = request.form.get("max_streams")
            try:
                max_streams = int(max_streams) if max_streams else None
            except ValueError:
                max_streams = None
            report_rows, text_report, pdf_report = process_camera_list(
                input_path, OUTPUT_FOLDER, max_streams
            )
            return render_template(
                "report.html",
                report_rows=report_rows,
                pdf_report=pdf_report,
                text_report=text_report
            )
    return render_template("upload.html")


@app.route("/download/<path:filename>")
def download_file(filename):
    """Serve files from the output directory as downloads."""
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
