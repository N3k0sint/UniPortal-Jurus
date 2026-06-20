import os
import markdown
from xhtml2pdf import pisa

def convert_md_to_pdf():
    print("[+] Starting Markdown to PDF conversion...")
    
    md_path = "/home/jurus/Documents/Project/UniPortal-Jurus/manual_setup_guide.md"
    pdf_path = "/home/jurus/Documents/Project/UniPortal-Jurus/manual_setup_guide.pdf"
    
    if not os.path.exists(md_path):
        print(f"[-] ERROR: Source markdown file not found at: {md_path}")
        return
        
    # Read Markdown content
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
        
    # Convert Markdown to HTML
    html_content = markdown.markdown(md_content, extensions=['fenced_code', 'codehilite'])
    
    # Wrap in standard HTML structure with custom CSS layout for the PDF print styling
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: a4;
                margin: 2cm;
            }}
            body {{
                font-family: Arial, sans-serif;
                font-size: 10.5pt;
                line-height: 1.6;
                color: #222222;
            }}
            h1 {{
                font-size: 20pt;
                color: #0d122b;
                border-bottom: 2px solid #1e70e6;
                padding-bottom: 5px;
                margin-bottom: 20px;
                text-align: center;
            }}
            h2 {{
                font-size: 14pt;
                color: #1e70e6;
                margin-top: 25px;
                margin-bottom: 10px;
                border-bottom: 1px solid #eeeeee;
                padding-bottom: 3px;
            }}
            h3 {{
                font-size: 11pt;
                color: #333333;
                margin-top: 15px;
            }}
            p {{
                margin-bottom: 10px;
            }}
            code {{
                font-family: Courier, monospace;
                background-color: #f4f4f4;
                padding: 2px 4px;
                font-size: 9.5pt;
            }}
            pre {{
                background-color: #f7f7f7;
                border: 1px solid #dddddd;
                padding: 10px;
                margin-bottom: 15px;
            }}
            pre code {{
                background-color: transparent;
                padding: 0;
                font-size: 9pt;
            }}
            blockquote {{
                background-color: #f9f9f9;
                border-left: 5px solid #d4af37;
                padding: 10px 15px;
                margin: 15px 0;
            }}
            ul {{
                margin-bottom: 15px;
                padding-left: 20px;
            }}
            li {{
                margin-bottom: 5px;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # Write PDF file
    with open(pdf_path, "wb") as f_out:
        pisa_status = pisa.CreatePDF(styled_html, dest=f_out)
        
    if pisa_status.err:
        print("[-] ERROR: Failed to generate PDF file.")
    else:
        print(f"[+] SUCCESS: PDF document created at: {pdf_path}")

if __name__ == "__main__":
    convert_md_to_pdf()
