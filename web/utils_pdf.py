from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, String, Rect, Circle
from reportlab.graphics.charts.piecharts import Pie
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape
from database import get_server_info, get_all_catalog_data

server_info = get_server_info()
catalogs = get_all_catalog_data()

# Palet warna laporan
NAVY = colors.HexColor("#172B4D")
BLUE = colors.HexColor("#176B87")
LIGHT_BLUE = colors.HexColor("#EAF2F8")
LIGHT_GREY = colors.HexColor("#F3F5F7")
MID_GREY = colors.HexColor("#667085")
DARK = colors.HexColor("#202B38")
BORDER = colors.HexColor("#D7DEE5")
GREEN = colors.HexColor("#237A57")
RED = colors.HexColor("#B42318")
AMBER = colors.HexColor("#9A6700")


def _text(value: Any, default: str = "-") -> str:
    """Mengubah nilai menjadi teks aman untuk Paragraph ReportLab."""
    if value is None or str(value).strip() == "":
        value = default

    return escape(str(value)).replace("\r\n", "\n").replace("\r", "\n").replace(
        "\n", "<br/>"
    )


def _status(value: Any) -> str:
    status = str(value or "PENDING").strip().upper()

    status_mapping = {
        "PENDING": "BELUM DITINJAU",
    }

    return status_mapping.get(status, status)


def _count_status(
    catalogs: list[dict[str, Any]],
    field: str,
    accepted: set[str],
) -> int:
    return sum(1 for item in catalogs if _status(item.get(field)) in accepted)


def format_timestamp(value: Any) -> str:
    """Memformat timestamp log."""
    if not value:
        return "-"

    try:
        timestamp = datetime.fromisoformat(str(value))
        return timestamp.strftime("%d-%m-%Y %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)
    

def _audit_percentage_chart(catalogs: list[dict[str, Any]]) -> Drawing:
    """Membuat grafik pie persentase status audit."""
    statuses = [
        ("Compliant", _count_status(catalogs, "status_audit", {"COMPLIANT"}), GREEN),
        ("Non-compliant", _count_status(catalogs, "status_audit", {"NON_COMPLIANT"}), RED),
        (
            "Pending / Lainnya",
            max(
                0,
                len(catalogs)
                - _count_status(catalogs, "status_audit", {"COMPLIANT"})
                - _count_status(catalogs, "status_audit", {"NON_COMPLIANT"}),
            ),
            AMBER,
        ),
    ]
    total = len(catalogs)
    drawing = Drawing(179 * mm, 51 * mm)

    if total == 0:
        drawing.add(
            Circle(
                27 * mm, 25.5 * mm, 17 * mm,
                fillColor=LIGHT_GREY, strokeColor=BORDER, strokeWidth=1,
            )
        )
        drawing.add(
            String(
                27 * mm, 24 * mm, "Tidak ada data",
                textAnchor="middle", fontName="Helvetica", fontSize=7,
                fillColor=MID_GREY,
            )
        )
        return drawing

    pie = Pie()
    pie.x = 7 * mm
    pie.y = 4 * mm
    pie.width = 43 * mm
    pie.height = 43 * mm
    pie.data = [count for _, count, _ in statuses]
    pie.labels = ["", "", ""]
    pie.simpleLabels = 0
    pie.sideLabels = 0
    pie.slices.strokeColor = colors.white
    pie.slices.strokeWidth = 1
    for index, (_, _, fill) in enumerate(statuses):
        pie.slices[index].fillColor = fill
    drawing.add(pie)

    # Legenda menampilkan jumlah dan persentase secara eksplisit.
    legend_y = [37 * mm, 23 * mm, 9 * mm]
    for (label, count, fill), y in zip(statuses, legend_y):
        percentage = (count / total) * 100
        drawing.add(
            Rect(
                65 * mm, y - 1.5 * mm, 4 * mm, 4 * mm,
                fillColor=fill, strokeColor=fill,
            )
        )
        drawing.add(
            String(
                73 * mm, y, f"{label}: {percentage:.1f}% ({count}/{total})",
                fontName="Helvetica", fontSize=8, fillColor=DARK,
            )
        )

    return drawing


def _page_footer(canvas, doc) -> None:
    """Menambahkan identitas dokumen dan nomor halaman."""
    canvas.saveState()
    page_width, _ = A4

    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, page_width - 18 * mm, 15 * mm)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MID_GREY)
    canvas.drawString(18 * mm, 10 * mm, "YORU-AGENT | CONFIDENTIAL")
    canvas.drawRightString(
        page_width - 18 * mm,
        10 * mm,
        f"Halaman {doc.page}",
    )
    canvas.restoreState()


def generate_pentest_pdf(
    output_filename: str | Path = "Yoru_Agent_Report.pdf",
) -> str:
    """
    Membuat laporan evaluasi keamanan server bergaya penetration testing.

    Seluruh data server dan katalog diambil langsung dari database.
    """

    server_info = get_server_info() or {}
    catalogs_data = get_all_catalog_data() or []

    catalogs = [
        item for item in catalogs_data
        if isinstance(item, dict)
    ]

    output_path = str(output_filename)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title="Yoru-Agent Server Security Assessment Report",
        author="Yoru-Agent",
        subject="Server security audit, hardening, and rollback activity",
    )

    sample = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=23,
            alignment=TA_LEFT,
            textColor=NAVY,
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=MID_GREY,
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "finding": ParagraphStyle(
            "FindingTitle",
            parent=sample["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=BLUE,
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=DARK,
            alignment=TA_JUSTIFY,
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "ReportSmall",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=DARK,
        ),
        "table_header": ParagraphStyle(
            "ReportTableHeader",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "ReportTableCell",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=DARK,
        ),
        "disclaimer": ParagraphStyle(
            "ReportDisclaimer",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=10,
            textColor=colors.HexColor("#475467"),
        ),
        "empty": ParagraphStyle(
            "ReportEmpty",
            parent=sample["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=11,
            textColor=MID_GREY,
        ),
    }

    def p(value: Any, style: ParagraphStyle = styles["table_cell"]) -> Paragraph:
        return Paragraph(_text(value), style)

    story = []
    generated_at = datetime.now().astimezone().strftime("%d %B %Y, %H:%M:%S %Z")

    # 1. Sampul ringkas dan informasi laporan
    story.append(Paragraph("YORU-AGENT", styles["title"]))
    story.append(
        Paragraph(
            "SERVER SECURITY ASSESSMENT &amp; HARDENING REPORT",
            ParagraphStyle(
                "ReportKicker",
                parent=styles["subtitle"],
                fontName="Helvetica-Bold",
                textColor=BLUE,
                fontSize=9,
            ),
        )
    )
    story.append(
        Paragraph(
            f"Laporan dibuat: {_text(generated_at)}",
            styles["subtitle"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.4,
            color=BLUE,
            spaceBefore=2,
            spaceAfter=9,
        )
    )

    info = server_info or {}
    if info:
        server_rows = [
            [p("Sistem Operasi"), p(info.get("os_platform") or info.get("sistem_operasi"))],
            [p("Arsitektur"), p(info.get("architecture") or info.get("arsitektur"))],
            [p("Hostname"), p(info.get("hostname"))],
        ]
        server_table = Table(server_rows, colWidths=[34 * mm, 145 * mm])
        server_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend(
            [
                Paragraph("Informasi Target", styles["section"]),
                server_table,
            ]
        )

    # 2. Executive summary audit
    total = len(catalogs)
    compliant = _count_status(catalogs, "status_audit", {"COMPLIANT"})
    non_compliant = _count_status(catalogs, "status_audit", {"NON_COMPLIANT"})
    audit_other = max(0, total - compliant - non_compliant)

    summary_data = [
        [p("TOTAL KONTROL", styles["table_header"]),
         p("COMPLIANT", styles["table_header"]),
         p("NON-COMPLIANT", styles["table_header"]),
         p("PENDING / LAINNYA", styles["table_header"])],
        [p(total), p(compliant), p(non_compliant), p(audit_other)],
    ]
    summary_table = Table(
        summary_data,
        colWidths=[44.75 * mm] * 4,
        hAlign="LEFT",
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, 1), LIGHT_GREY),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("TEXTCOLOR", (1, 1), (1, 1), GREEN),
                ("TEXTCOLOR", (2, 1), (2, 1), RED),
                ("FONTSIZE", (0, 1), (-1, 1), 12),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story.append(Paragraph("1. Ringkasan Eksekutif", styles["section"]))
    story.append(
        p(
            "Bagian ini merangkum hasil pemeriksaan kontrol keamanan yang "
            "tercatat pada database Yoru-Agent pada saat laporan dibuat. "
            "Status audit ditampilkan sesuai hasil terakhir yang tersimpan."
        , styles["body"])
    )
    story.append(summary_table)
    story.append(Spacer(1, 7))
    story.append(Paragraph("Persentase Status Audit", styles["finding"]))
    story.append(_audit_percentage_chart(catalogs))
    story.append(Spacer(1, 5))

    hardening_success = _count_status(catalogs, "status_hardening", {"SUCCESS"})
    hardening_skipped = _count_status(catalogs, "status_hardening", {"SKIPPED"})
    hardening_failed = _count_status(catalogs, "status_hardening", {"FAILED"})
    rollback_success = _count_status(catalogs, "status_rollback", {"SUCCESS"})
    rollback_skipped = _count_status(catalogs, "status_rollback", {"SKIPPED"})
    rollback_failed = _count_status(catalogs, "status_rollback", {"FAILED"})

    remediation_data = [
        [p("HARDENING BERHASIL", styles["table_header"]),
         p("HARDENING SKIPPED", styles["table_header"]),
         p("HARDENING GAGAL", styles["table_header"]),
         p("ROLLBACK BERHASIL", styles["table_header"]),
         p("ROLLBACK SKIPPED", styles["table_header"]),
         p("ROLLBACK GAGAL", styles["table_header"])],
        [p(hardening_success), p(hardening_skipped), p(hardening_failed),
         p(rollback_success), p(rollback_skipped), p(rollback_failed)],
    ]
    remediation_table = Table(
        remediation_data,
        colWidths=[29.83 * mm] * 6,
        hAlign="LEFT",
    )
    remediation_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BLUE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(Spacer(1, 7))
    story.append(remediation_table)

    # 3. Metodologi dan batasan laporan
    story.append(Paragraph("2. Ruang Lingkup dan Batasan", styles["section"]))
    story.append(
        p(
            "Laporan ini menyajikan hasil audit kontrol keamanan server serta "
            "riwayat tindakan hardening dan rollback yang tercatat pada basis data "
            "lokal. Acuan CIS Benchmarks dan UU PDP digunakan sebagai referensi "
            "pemetaan kontrol teknis. Laporan ini bukan pengganti penetration test "
            "menyeluruh, audit kepatuhan hukum, atau verifikasi independen atas "
            "seluruh infrastruktur organisasi.",
            styles["body"],
        )
    )

    # 4. Detail temuan dan riwayat aktivitas
    story.append(Paragraph("3. Detail Hasil Audit dan Riwayat Remediasi", styles["section"]))

    if not catalogs:
        story.append(
            p(
                "Tidak terdapat data katalog yang tersedia pada database "
                "untuk periode pembuatan laporan ini.",
                styles["empty"],
            )
        )

    for index, catalog in enumerate(catalogs, start=1):
        rule_id = catalog.get("id", "-")
        name = catalog.get("nama", "Nama kontrol tidak tersedia")
        risk = catalog.get("risiko", "-")
        category = catalog.get("kategori", "-")
        cis_code = catalog.get("kode_cis")
        cis_title = catalog.get("judul_cis")
        cis_version = catalog.get("versi_cis")
        framework = catalog.get("framework")
        regulasi = catalog.get("regulasi")
        kepatuhan = catalog.get("kepatuhan")
        audit_status = _status(catalog.get("status_audit"))
        audit_only = catalog.get("audit_only", False)

        # Katalog non-CIS tetap menampilkan framework dan dasar regulasinya.
        has_cis = bool(cis_code and str(cis_code).strip() not in {"-", "N/A", "None"})
        cis_code_label = cis_code if has_cis else "Non-CIS"
        description = catalog.get("deskripsi", "-")

        heading = Paragraph(
            f"{index}. {_text(rule_id)} - {_text(name)}",
            styles["finding"],
        )

        metadata = [
            [p("KODE CIS", styles["table_header"]),
             p("KATEGORI", styles["table_header"]),
             p("TINGKAT RISIKO", styles["table_header"]),
             p("STATUS AUDIT", styles["table_header"])],
            [p(cis_code_label), p(category), p(risk), p(audit_status)],
        ]
        metadata_table = Table(
            metadata,
            colWidths=[34 * mm, 54 * mm, 42 * mm, 48 * mm],
        )
        metadata_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("BACKGROUND", (0, 1), (-1, 1), LIGHT_GREY),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        detail_parts = [heading, metadata_table]

        if has_cis and cis_title:
            detail_parts.extend(
                [
                    Spacer(1, 4),
                    Paragraph(
                        f"<b>Referensi CIS:</b> {escape(str(cis_title))}",
                        styles["body"],
                    ),
                    Paragraph(
                        f"<b>Versi CIS:</b> {escape(str(cis_version or '-'))}",
                        styles["body"],
                    ),
                ]
            )

        # Tampilkan framework dan dasar UU PDP untuk semua katalog,
        # termasuk katalog yang tidak memiliki kode CIS.
        regulatory_rows = [
            [
                p("FRAMEWORK / ACUAN", styles["table_header"]),
                p("REGULASI DAN KEPATUHAN", styles["table_header"]),
            ],
            [
                p(framework or ("CIS Benchmark" if has_cis else "Tidak ditentukan")),
                p(
                    "Regulasi: " + str(regulasi or "-")
                    + "\nKepatuhan: " + str(kepatuhan or "-")
                ),
            ],
        ]
        regulatory_table = Table(
            regulatory_rows,
            colWidths=[68 * mm, 110 * mm],
        )
        regulatory_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                    ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BLUE),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        detail_parts.extend(
            [
                Spacer(1, 5),
                regulatory_table,
                Spacer(1, 4),
                Paragraph(
                    f"<b>Deskripsi kontrol:</b> {escape(str(description or '-'))}",
                    styles["body"],
                ),
                Spacer(1, 4),
            ]
        )

        if audit_only:
            detail_parts.extend([
                Spacer(1, 8),
                Paragraph(
                    f"<b>Keterangan:</b> Katalog ini hanya mendukung operasi audit. "
                    "Operasi hardening dan rollback tidak tersedia karena "
                    "penerapannya berpotensi mengganggu layanan server "
                    "yang sedang berjalan.",
                    styles["body"],
                ),
            ])

        
        story.append(KeepTogether(detail_parts))


        activity_rows = [
            [
                p("AKTIVITAS", styles["table_header"]),
                p("STATUS", styles["table_header"]),
                p("WAKTU", styles["table_header"]),
                p("AKTIVITAS TERAKHIR / LOG", styles["table_header"]),
            ],
            [
                p("Audit"),
                p(audit_status),
                p(format_timestamp(catalog.get("waktu_audit"))),
                p(catalog.get("log_audit_terakhir") or "Belum ada catatan hasil audit tersimpan."),
            ],
        ]

        if not audit_only:
            activity_rows.append(
                [
                    p("Hardening"),
                    p(_status(catalog.get("status_hardening"))),
                    p(format_timestamp(catalog.get("waktu_hardening"))),
                    p(catalog.get("log_hardening_terakhir") or "Belum ada log hardening tersimpan."),
                ]
            )
            activity_rows.append(
                [
                    p("Rollback"),
                    p(_status(catalog.get("status_rollback"))),
                    p(format_timestamp(catalog.get("waktu_rollback"))),
                    p(catalog.get("log_rollback_terakhir") or "Belum ada log rollback tersimpan."),
                ]
            )

        activity_table = Table(
            activity_rows,
            colWidths=[24 * mm, 28 * mm, 34 * mm, 92 * mm],
            repeatRows=1,
            hAlign="LEFT",
        )
        activity_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(activity_table)
        story.append(Spacer(1, 8))

    # 5. Disclaimer legal
    story.append(Paragraph("4. Catatan Legal dan Afiliasi", styles["section"]))
    disclaimer = (
        "<b>Pernyataan Legal dan Afiliasi.</b> Yoru-Agent dikembangkan dan "
        "digunakan secara independen untuk mendukung evaluasi keamanan teknis "
        "serta pemetaan kontrol terhadap CIS Benchmarks dan ketentuan "
        "Undang-Undang Pelindungan Data Pribadi (UU PDP) di Indonesia. "
        "Penyebutan CIS Benchmarks maupun UU PDP dalam laporan ini semata-mata "
        "merupakan referensi pemetaan dan tidak menyiratkan adanya dukungan, "
        "pengesahan, sponsorship, kemitraan, atau afiliasi resmi dengan "
        "Center for Internet Security (CIS), instansi pemerintah, maupun "
        "lembaga penegak hukum mana pun. Hasil pemetaan merupakan analisis "
        "teknis dalam ruang lingkup proyek dan tidak dapat ditafsirkan sebagai "
        "sertifikasi CIS, pendapat hukum, atau pernyataan resmi dari lembaga "
        "yang disebutkan."
    )
    disclaimer_table = Table(
        [[Paragraph(disclaimer, styles["disclaimer"])]],
        colWidths=[179 * mm],
    )
    disclaimer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                ("LINEBEFORE", (0, 0), (0, -1), 3, BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(disclaimer_table)

    doc.build(
        story,
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
    )

    return output_path
