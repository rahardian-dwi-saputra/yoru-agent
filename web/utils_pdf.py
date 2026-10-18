import hashlib

# --- PATCH UNTUK MENGATASI ERROR usedforsecurity ---
_orig_md5 = hashlib.md5
def _patched_md5(*args, **kwargs):
    kwargs.pop('usedforsecurity', None)
    return _orig_md5(*args, **kwargs)
hashlib.md5 = _patched_md5

from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_pentest_pdf(catalogs_data, output_filename="Yoru_Agent_Pentest_Report.pdf"):
    """Menghasilkan file PDF laporan audit ala pentesting dari data katalog."""
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        rightMargin=40, leftMargin=40,
        topMargin=40, bottomMargin=40
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor("#1e1e24"),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#6c757d"),
        spaceAfter=15
    )
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor("#2c3e50"),
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        leading=13
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#555555"),
        leading=11
    )

    # 1. Header Laporan
    story.append(Paragraph("YORU-AGENT: SECURITY AUDIT & PENTEST REPORT", title_style))
    generated_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    story.append(Paragraph(f"Generated on: {generated_time} | Target: Ubuntu Server (CIS Benchmarks)", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#3498db"), spaceAfter=15))

    # 2. Hitung Statistik Ringkasan (Executive Summary)
    total_rules = len(catalogs_data)
    compliant_count = sum(1 for c in catalogs_data if c.get('status_audit') == 'COMPLIANT')
    non_compliant_count = sum(1 for c in catalogs_data if c.get('status_audit') == 'NON_COMPLIANT')
    other_count = total_rules - (compliant_count + non_compliant_count)

    summary_data = [
        [Paragraph("<b>Total Rules</b>", body_style), Paragraph("<b>COMPLIANT</b>", body_style), Paragraph("<b>NON_COMPLIANT</b>", body_style), Paragraph("<b>PENDING / LAINNYA</b>", body_style)],
        [str(total_rules), str(compliant_count), str(non_compliant_count), str(other_count)]
    ]
    
    summary_table = Table(summary_data, colWidths=[130, 130, 130, 140])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f8f9fa")),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TEXTCOLOR', (0,1), (1,1), colors.HexColor("#27ae60")),
        ('TEXTCOLOR', (2,1), (2,1), colors.HexColor("#c0392b")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#dee2e6")),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    
    story.append(Paragraph("Executive Summary", section_heading))
    story.append(summary_table)
    story.append(Spacer(1, 15))

    # 3. Detail Temuan per Katalog
    story.append(Paragraph("Detailed Audit & Remediation Findings", section_heading))
    
    table_data = [[
        Paragraph("<b>ID / CIS</b>", body_style),
        Paragraph("<b>Rule & Kategori</b>", body_style),
        Paragraph("<b>Status Audit</b>", body_style),
        Paragraph("<b>Deskripsi & Riwayat Action</b>", body_style)
    ]]

    for cat in catalogs_data:
        rule_id = cat.get('id', '-')
        kode_cis = cat.get('kode_cis', '-')
        nama = cat.get('nama', '-')
        kategori = cat.get('kategori', '-')
        status_audit = cat.get('status_audit', 'PENDING')
        
        # Bersihkan deskripsi dari newline
        raw_desc = cat.get('deskripsi', '-')
        clean_desc = raw_desc.replace('\n', ' ') if raw_desc else '-'
        
        # Ambil status dan waktu hardening & rollback
        s_hard = cat.get('status_hardening', '-')
        w_hard = cat.get('waktu_hardening', '-')
        s_roll = cat.get('status_rollback', '-')
        w_roll = cat.get('waktu_rollback', '-')

        # Susun teks riwayat action
        history_text = f"<br/><br/><b>Riwayat Action:</b><br/>" \
                       f"- Hardening: <b>{s_hard}</b> ({w_hard})<br/>" \
                       f"- Rollback: <b>{s_roll}</b> ({w_roll})"

        full_desc_cell = f"<b>{nama}</b> ({kategori})<br/>{clean_desc}{history_text}"

        table_data.append([
            Paragraph(f"<b>{rule_id}</b><br/><font color='#666'>CIS: {kode_cis}</font>", meta_style),
            Paragraph(f"<b>{kategori}</b>", meta_style),
            Paragraph(f"<b>{status_audit}</b>", meta_style),
            Paragraph(full_desc_cell, body_style)
        ])

    findings_table = Table(table_data, colWidths=[70, 85, 95, 280])
    findings_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#34495e")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#bdc3c7")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#fdfefe")])
    ]))

    # Perbaikan warna header teks tabel
    for i in range(4):
        table_data[0][i] = Paragraph(f"<font color='white'><b>{table_data[0][i].text.replace('<b>','').replace('</b>','')}</b></font>", body_style)

    story.append(findings_table)
    
    doc.build(story)
    return output_filename