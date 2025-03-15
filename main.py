from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
import pandas as pd
from datetime import datetime
from io import BytesIO
from typing import List, Optional
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


app = FastAPI()

# Enable logging for debugging
logging.basicConfig(level=logging.INFO)

# ---------------------------
# Define Pydantic Model with English Field Names
# ---------------------------
class LeadData(BaseModel):
    salesperson: str
    customer_type: str
    industry: Optional[str] = None
    meeting_count: int
    adhesive_type: Optional[str] = None
    opportunity: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    contact_date: Optional[str] = None
    contact_details: Optional[str] = None
    contact_type: Optional[str] = None

# ---------------------------
# Debugging Endpoint
# ---------------------------
@app.post("/debug_request")
async def debug_request(request: Request):
    """Logs incoming request body to help debug issues"""
    try:
        body = await request.json()
        logging.info(f"Received JSON: {body}")
        return {"message": "Request received", "body": body}
    except Exception as e:
        logging.error(f"Error in JSON request: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

# ---------------------------
# FastAPI Endpoint
# ---------------------------
@app.post("/generate_pdf")
async def generate_report(request: Request):
    """
    Accepts JSON data, processes it, and returns a PDF report.
    """
    try:
        body = await request.json()
        logging.info(f"Received JSON: {body}")

        # Validate data using Pydantic
        data = [LeadData(**item) for item in body]
        logging.info(f"Parsed Data: {data}")

        # Convert to DataFrame
        df = pd.DataFrame([lead.dict() for lead in data])
        logging.info(f"DataFrame Structure:\n{df.dtypes}")

        # Ensure "contact_date" is parsed correctly
        if "contact_date" in df.columns:
            df["contact_date"] = pd.to_datetime(df["contact_date"], errors="coerce").dt.strftime("%Y-%m-%d")
            logging.info(f"Transformed Dates: {df['contact_date']}")

        # Process Data
        salespersons = process_data(df.to_dict(orient="records"))
        pdf_output = generate_pdf(salespersons)

        return StreamingResponse(pdf_output, media_type="application/pdf",
                                 headers={"Content-Disposition": "attachment; filename=CRM_Report.pdf"})
    except ValidationError as ve:
        logging.error(f"Validation Error: {ve.errors()}")
        raise HTTPException(status_code=422, detail=ve.errors())
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
def process_data(data):
    """Processes input data and structures it for reporting"""
    df = pd.DataFrame(data)

    # Filter out customers labeled as 'Regular Customer'
    df = df[df['customer_type'] != 'Regular Customer']

    # Convert meeting count to int
    df['meeting_count'] = pd.to_numeric(df['meeting_count'], errors='coerce').fillna(0).astype(int)

    salespersons = {}

    for sp in df['salesperson'].unique():
        sp_data = df[df['salesperson'] == sp]

        existing_customers = sp_data[sp_data['customer_type'] == 'Existing Customer'].shape[0]
        prospective_customers = sp_data[sp_data['customer_type'] == 'Prospective Customer'].shape[0]

        industry_breakdown = {}
        for _, row in sp_data.iterrows():
            industry = row['industry'] if pd.notnull(row['industry']) else "(Not Specified)"
            customer_type = row['customer_type']

            # Ensure the industry key exists
            if industry not in industry_breakdown:
                industry_breakdown[industry] = {'Existing Customer': 0, 'Prospective Customer': 0}

            # Ensure customer_type key exists before incrementing
            if customer_type in industry_breakdown[industry]:
                industry_breakdown[industry][customer_type] += 1
            else:
                industry_breakdown[industry][customer_type] = 1  # Initialize to 1

        meeting_total = sp_data['meeting_count'].sum()

        salespersons[sp] = {
            'existing_customers': existing_customers,
            'prospective_customers': prospective_customers,
            'industry_breakdown': industry_breakdown,
            'meeting_total': meeting_total,
        }

    return salespersons


def generate_pdf(salespersons):
    """Generates a PDF report from the processed data"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica", 14)  # Use a standard font
    y = height - 40

    # Title
    c.drawString(200, y, "CRM Sales Report")
    y -= 30

    for sp, info in salespersons.items():
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, f"Salesperson: {sp}")
        y -= 20

        c.setFont("Helvetica", 12)
        c.drawString(70, y, f"Existing Customers: {info['existing_customers']} | Prospective Customers: {info['prospective_customers']}")
        y -= 20

        c.drawString(70, y, "Industry Breakdown:")
        y -= 20

        for industry, counts in info['industry_breakdown'].items():
            c.drawString(90, y, f"- {industry}: Existing {counts['Existing Customer']}, Prospective {counts['Prospective Customer']}")
            y -= 15

        c.drawString(70, y, f"Total Meetings: {info['meeting_total']}")
        y -= 30

        if y < 50:
            c.showPage()
            y = height - 40

    c.save()
    buffer.seek(0)
    return buffer

