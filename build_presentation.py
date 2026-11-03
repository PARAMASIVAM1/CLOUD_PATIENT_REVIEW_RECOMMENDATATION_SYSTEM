import os
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

# Set MPLCONFIGDIR
temp_mpl = os.path.join(os.getcwd(), 'tmp_mpl')
os.makedirs(temp_mpl, exist_ok=True)
os.environ['MPLCONFIGDIR'] = temp_mpl

def generate_diagrams():
    assets_dir = os.path.join(os.getcwd(), "presentation_assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    # 1. USE CASE DIAGRAM
    fig, ax = plt.subplots(figsize=(10, 6), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis('off')
    
    sys_box = patches.FancyBboxPatch((2.2, 0.3), 5.6, 5.4, boxstyle="round,pad=0.2",
                                     ec="#0d9488", fc="#f0fdfa", lw=2, linestyle='--')
    ax.add_patch(sys_box)
    ax.text(5.0, 5.45, "Healthcare AI System Boundary", ha='center', va='center',
            fontsize=12, fontweight='bold', color="#0f766e")
    
    actors = [
        ("Patient", 0.9, 4.0, "#0284c7"),
        ("Doctor", 0.9, 1.8, "#16a34a"),
        ("Admin", 9.1, 3.0, "#8b5cf6")
    ]
    for name, x, y, col in actors:
        circle = patches.Circle((x, y + 0.3), 0.22, ec=col, fc=col, lw=1.5)
        ax.add_patch(circle)
        ax.plot([x, x], [y + 0.08, y - 0.25], color=col, lw=2)
        ax.plot([x - 0.2, x + 0.2], [y, y], color=col, lw=2)
        ax.plot([x, x - 0.18], [y - 0.25, y - 0.5], color=col, lw=2)
        ax.plot([x, x + 0.18], [y - 0.25, y - 0.5], color=col, lw=2)
        ax.text(x, y - 0.72, name, ha='center', va='center', fontsize=10, fontweight='bold', color=col)
        
    patient_cases = [
        ("Register / Login Account", 3.6, 4.8),
        ("Search Doctors (NLP Symptoms)", 3.6, 4.0),
        ("Book Medical Appointment", 3.6, 3.2),
        ("Download Appointment Letter", 3.6, 2.4),
        ("Submit Consultation Feedback", 3.6, 1.6),
    ]
    doctor_cases = [
        ("Review & Approve Visits", 6.4, 4.2),
        ("Record Treatment Completed", 6.4, 3.4),
        ("View Anonymized Reviews", 6.4, 2.6),
        ("Respond / Report Feedback", 6.4, 1.8),
    ]
    admin_cases = [
        ("Moderate Reviews & Content", 5.0, 1.0),
        ("Monitor System Audit Logs", 5.0, 0.45)
    ]
    
    for label, x, y in patient_cases + doctor_cases + admin_cases:
        ellipse = patches.Ellipse((x, y), 2.1, 0.52, ec="#334155", fc="#ffffff", lw=1.2)
        ax.add_patch(ellipse)
        ax.text(x, y, label, ha='center', va='center', fontsize=7.5, color="#0f172a", fontweight='medium')
        
    for _, x, y in patient_cases:
        ax.plot([1.2, x - 1.05], [4.0, y], color="#94a3b8", lw=1)
    for _, x, y in doctor_cases:
        ax.plot([1.2, 5.35], [1.8, y], color="#94a3b8", lw=1)
    for _, x, y in doctor_cases + admin_cases:
        ax.plot([8.8, x + 1.05], [3.0, y], color="#94a3b8", lw=1)
        
    plt.tight_layout()
    p1 = os.path.join(assets_dir, "use_case_diagram.png")
    plt.savefig(p1, bbox_inches='tight', dpi=220)
    plt.close()
    
    # 2. DFD LEVEL 0
    fig, ax = plt.subplots(figsize=(10, 5), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis('off')
    
    center_circle = patches.Circle((5.0, 2.5), 1.3, ec="#0284c7", fc="#e0f2fe", lw=2.5)
    ax.add_patch(center_circle)
    ax.text(5.0, 2.7, "0.0\nHealthcare AI System", ha='center', va='center', fontsize=11, fontweight='bold', color="#0369a1")
    ax.text(5.0, 2.1, "(Recommendation &\nReview Portal)", ha='center', va='center', fontsize=8.5, color="#475569")
    
    p_box = patches.FancyBboxPatch((0.5, 2.0), 1.8, 1.0, boxstyle="square,pad=0.1", ec="#0284c7", fc="#f8fafc", lw=2)
    ax.add_patch(p_box)
    ax.text(1.4, 2.5, "PATIENT", ha='center', va='center', fontsize=10, fontweight='bold', color="#0284c7")
    
    d_box = patches.FancyBboxPatch((7.7, 3.2), 1.8, 1.0, boxstyle="square,pad=0.1", ec="#16a34a", fc="#f8fafc", lw=2)
    ax.add_patch(d_box)
    ax.text(8.6, 3.7, "DOCTOR", ha='center', va='center', fontsize=10, fontweight='bold', color="#16a34a")
    
    a_box = patches.FancyBboxPatch((7.7, 0.8), 1.8, 1.0, boxstyle="square,pad=0.1", ec="#8b5cf6", fc="#f8fafc", lw=2)
    ax.add_patch(a_box)
    ax.text(8.6, 1.3, "ADMINISTRATOR", ha='center', va='center', fontsize=10, fontweight='bold', color="#8b5cf6")
    
    ax.annotate("Symptoms, Booking, Feedback", xy=(3.7, 2.8), xytext=(2.3, 2.8),
                arrowprops=dict(arrowstyle="->", color="#0284c7", lw=1.5), fontsize=7.5, color="#1e293b", va='bottom')
    ax.annotate("Doctor Matches, Booking Letter", xy=(2.3, 2.2), xytext=(3.7, 2.2),
                arrowprops=dict(arrowstyle="->", color="#0284c7", lw=1.5), fontsize=7.5, color="#1e293b", va='top')
                
    ax.annotate("Consultation Status, Notes", xy=(6.2, 3.2), xytext=(7.7, 3.5),
                arrowprops=dict(arrowstyle="->", color="#16a34a", lw=1.5), fontsize=7.5, color="#1e293b", va='bottom')
    ax.annotate("Anonymized Reviews, Requests", xy=(7.7, 3.2), xytext=(6.2, 2.8),
                arrowprops=dict(arrowstyle="->", color="#16a34a", lw=1.5), fontsize=7.5, color="#1e293b", va='top')
                
    ax.annotate("Moderation Decisions, CRUD", xy=(6.2, 1.8), xytext=(7.7, 1.5),
                arrowprops=dict(arrowstyle="->", color="#8b5cf6", lw=1.5), fontsize=7.5, color="#1e293b", va='bottom')
    ax.annotate("Audit Logs, System Analytics", xy=(7.7, 1.1), xytext=(6.2, 1.4),
                arrowprops=dict(arrowstyle="->", color="#8b5cf6", lw=1.5), fontsize=7.5, color="#1e293b", va='top')

    plt.tight_layout()
    p2 = os.path.join(assets_dir, "dfd_level_0.png")
    plt.savefig(p2, bbox_inches='tight', dpi=220)
    plt.close()
    
    # 3. DFD LEVEL 1
    fig, ax = plt.subplots(figsize=(10, 6.2), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.2)
    ax.axis('off')
    
    procs = [
        ("1.0 Auth &\nProfile", 1.8, 4.8),
        ("2.0 NLP Doctor\nRecommendation", 5.0, 4.8),
        ("3.0 Appointment\nLifecycle", 8.2, 4.8),
        ("4.0 NLP Sentiment\n& Review Engine", 5.0, 2.2),
        ("5.0 Admin &\nModeration", 8.2, 2.2),
    ]
    for label, x, y in procs:
        c = patches.Circle((x, y), 0.75, ec="#0d9488", fc="#ccfbf1", lw=2)
        ax.add_patch(c)
        ax.text(x, y, label, ha='center', va='center', fontsize=8, fontweight='bold', color="#0f766e")
        
    stores = [
        ("D1: Patients Store", 1.8, 3.5),
        ("D2: Doctors Dataset (26k)", 5.0, 3.5),
        ("D3: Appointments Store", 8.2, 3.5),
        ("D4: Patient Reviews", 3.0, 0.8),
        ("D5: System Audit Logs", 7.0, 0.8),
    ]
    for label, x, y in stores:
        r = patches.Rectangle((x - 1.1, y - 0.25), 2.2, 0.5, ec="#475569", fc="#f8fafc", lw=1.5)
        ax.add_patch(r)
        ax.plot([x - 1.1, x - 1.1], [y - 0.25, y + 0.25], color="#475569", lw=3)
        ax.text(x, y, label, ha='center', va='center', fontsize=7.5, fontweight='bold', color="#334155")
        
    ax.annotate("", xy=(1.8, 3.75), xytext=(1.8, 4.05), arrowprops=dict(arrowstyle="<->", color="#0f766e", lw=1.2))
    ax.annotate("", xy=(5.0, 3.75), xytext=(5.0, 4.05), arrowprops=dict(arrowstyle="<->", color="#0f766e", lw=1.2))
    ax.annotate("", xy=(8.2, 3.75), xytext=(8.2, 4.05), arrowprops=dict(arrowstyle="<->", color="#0f766e", lw=1.2))
    ax.annotate("", xy=(3.8, 1.05), xytext=(4.5, 1.6), arrowprops=dict(arrowstyle="->", color="#0f766e", lw=1.2))
    ax.annotate("", xy=(7.4, 1.05), xytext=(8.0, 1.6), arrowprops=dict(arrowstyle="->", color="#0f766e", lw=1.2))
    ax.annotate("Completed Visit", xy=(5.75, 2.4), xytext=(7.5, 4.3),
                arrowprops=dict(arrowstyle="->", color="#0284c7", lw=1.2), fontsize=7, color="#0284c7")

    plt.tight_layout()
    p3 = os.path.join(assets_dir, "dfd_level_1.png")
    plt.savefig(p3, bbox_inches='tight', dpi=220)
    plt.close()
    
    # 4. SEQUENCE DIAGRAM
    fig, ax = plt.subplots(figsize=(10, 5.8), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')
    
    lifelines = [
        ("Patient", 1.2, "#0284c7"),
        ("Flask Portal", 3.7, "#0d9488"),
        ("NLP Model", 6.2, "#8b5cf6"),
        ("PostgreSQL", 8.8, "#1e293b")
    ]
    for name, x, col in lifelines:
        box = patches.FancyBboxPatch((x - 0.9, 9.2), 1.8, 0.6, boxstyle="round,pad=0.1", ec=col, fc=col, lw=1.5)
        ax.add_patch(box)
        ax.text(x, 9.5, name, ha='center', va='center', fontsize=9, fontweight='bold', color="#ffffff")
        ax.plot([x, x], [0.3, 9.2], color="#cbd5e1", lw=1.5, linestyle="--")
        
    messages = [
        (8.5, 1.2, 3.7, "1. Book Appointment Request", False, "#0284c7"),
        (7.8, 3.7, 8.8, "2. INSERT appointments (Pending)", False, "#0d9488"),
        (7.1, 8.8, 3.7, "3. Confirm appointment_ref", True, "#64748b"),
        (6.4, 3.7, 8.8, "4. Doctor completes consultation", False, "#16a34a"),
        (5.7, 1.2, 3.7, "5. Submit Feedback (Rating & Text)", False, "#0284c7"),
        (5.0, 3.7, 6.2, "6. predict_sentiment(feedback_text)", False, "#8b5cf6"),
        (4.3, 6.2, 3.7, "7. Returns 'Positive' Sentiment", True, "#8b5cf6"),
        (3.6, 3.7, 8.8, "8. INSERT patient_reviews (Anonymized)", False, "#0d9488"),
        (2.9, 8.8, 3.7, "9. Return review_id & auto-sync", True, "#64748b"),
        (2.2, 3.7, 1.2, "10. Feedback Confirmation", True, "#0284c7"),
        (1.5, 3.7, 8.8, "11. Doctor loads dashboard metrics", False, "#16a34a"),
        (0.8, 8.8, 3.7, "12. Render Anonymized Review card", True, "#0d9488"),
    ]
    for y, x1, x2, txt, is_dashed, col in messages:
        ax.annotate("", xy=(x2, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.3, linestyle="dashed" if is_dashed else "solid"))
        mid_x = (x1 + x2) / 2
        ax.text(mid_x, y + 0.16, txt, ha='center', va='bottom', fontsize=7.2, fontweight='medium', color="#1e293b")
        
    plt.tight_layout()
    p4 = os.path.join(assets_dir, "sequence_diagram.png")
    plt.savefig(p4, bbox_inches='tight', dpi=220)
    plt.close()
    
    # 5. DEPLOYMENT DIAGRAM
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis('off')
    
    b1 = patches.FancyBboxPatch((0.4, 1.5), 2.2, 3.6, boxstyle="round,pad=0.2", ec="#0284c7", fc="#f0f9ff", lw=1.8)
    ax.add_patch(b1)
    ax.text(1.5, 4.8, "CLIENT TIER\n(Desktop / Mobile)", ha='center', va='center', fontsize=9.5, fontweight='bold', color="#0284c7")
    ax.text(1.5, 3.6, "• HTML5 / CSS3\n• Modern Dashboard\n• Patient Portal\n• Doctor Care Portal\n• Admin Dashboard",
            ha='center', va='center', fontsize=8, color="#334155")
            
    b2 = patches.FancyBboxPatch((3.7, 1.5), 2.7, 3.6, boxstyle="round,pad=0.2", ec="#0d9488", fc="#f0fdfa", lw=1.8)
    ax.add_patch(b2)
    ax.text(5.05, 4.8, "RENDER WEB SERVICE\n(healthcare-ai-portal)", ha='center', va='center', fontsize=9.5, fontweight='bold', color="#0f766e")
    ax.text(5.05, 3.6, "• Python 3.11 Runtime\n• Gunicorn (2 Workers)\n• Flask MVC Framework\n• SBERT / NLP Model\n• db.py Auto-Healing\n• REST Endpoints",
            ha='center', va='center', fontsize=8, color="#334155")
            
    b3 = patches.FancyBboxPatch((7.4, 1.5), 2.2, 3.6, boxstyle="round,pad=0.2", ec="#1e293b", fc="#f8fafc", lw=1.8)
    ax.add_patch(b3)
    ax.text(8.5, 4.8, "MANAGED DATABASE\n(healthcare-db)", ha='center', va='center', fontsize=9.5, fontweight='bold', color="#1e293b")
    ax.text(8.5, 3.6, "• PostgreSQL 16\n• 26,712 Doctors Table\n• Appointments Store\n• Patient Reviews\n• SSL Encryption\n• High-Speed Pool",
            ha='center', va='center', fontsize=8, color="#334155")
            
    ax.annotate("HTTPS / Port 443\n(SSL Edge Gateway)", xy=(3.7, 3.3), xytext=(2.6, 3.3),
                arrowprops=dict(arrowstyle="<->", color="#0284c7", lw=1.8), fontsize=7.5, color="#0369a1", ha='center', va='bottom')
    ax.annotate("PostgreSQL TCP 5432\n(DATABASE_URL)", xy=(7.4, 3.3), xytext=(6.4, 3.3),
                arrowprops=dict(arrowstyle="<->", color="#0d9488", lw=1.8), fontsize=7.5, color="#0f766e", ha='center', va='bottom')
                
    git_box = patches.FancyBboxPatch((3.7, 5.3), 2.7, 0.6, boxstyle="round,pad=0.1", ec="#475569", fc="#ffffff", lw=1.2)
    ax.add_patch(git_box)
    ax.text(5.05, 5.6, "GitHub CI/CD: origin/main", ha='center', va='center', fontsize=8, fontweight='bold', color="#1e293b")
    ax.annotate("", xy=(5.05, 5.1), xytext=(5.05, 5.3), arrowprops=dict(arrowstyle="->", color="#475569", lw=1.5, linestyle="dashed"))

    plt.tight_layout()
    p5 = os.path.join(assets_dir, "deployment_diagram.png")
    plt.savefig(p5, bbox_inches='tight', dpi=220)
    plt.close()
    
    print("[SUCCESS] All 5 diagram images created successfully.")
    return p1, p2, p3, p4, p5

def build_presentation(img_usecase, img_dfd0, img_dfd1, img_seq, img_deploy):
    prs = Presentation()
    # 16:9 Widescreen dimensions: 13.333 x 7.5 inches
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]
    
    # Color Palette
    PRIMARY_DARK = RGBColor(10, 25, 47)    # #0a192f
    TEAL_ACCENT  = RGBColor(13, 148, 136)  # #0d9488
    SKY_BLUE     = RGBColor(2, 132, 199)   # #0284c7
    SLATE_TEXT   = RGBColor(51, 65, 85)    # #334155
    LIGHT_BG     = RGBColor(248, 250, 252) # #f8fafc
    WHITE        = RGBColor(255, 255, 255)
    MUTED_GRAY   = RGBColor(148, 163, 184)
    
    def add_header(slide, title_text, category="HEALTHCARE AI SYSTEM ARCHITECTURE"):
        banner = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(1.15))
        banner.fill.solid()
        banner.fill.fore_color.rgb = PRIMARY_DARK
        banner.line.color.rgb = TEAL_ACCENT
        banner.line.width = Pt(2)
        
        tb_cat = slide.shapes.add_textbox(Inches(0.8), Inches(0.12), Inches(11.7), Inches(0.3))
        p_cat = tb_cat.text_frame.paragraphs[0]
        p_cat.text = category.upper()
        p_cat.font.size = Pt(10)
        p_cat.font.bold = True
        p_cat.font.color.rgb = TEAL_ACCENT
        
        tb_title = slide.shapes.add_textbox(Inches(0.8), Inches(0.38), Inches(11.7), Inches(0.65))
        p_title = tb_title.text_frame.paragraphs[0]
        p_title.text = title_text
        p_title.font.size = Pt(22)
        p_title.font.bold = True
        p_title.font.color.rgb = WHITE
        
        footer = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(7.15), Inches(13.333), Inches(0.35))
        footer.fill.solid()
        footer.fill.fore_color.rgb = RGBColor(15, 23, 42)
        footer.line.fill.background()
        
        tb_foot = slide.shapes.add_textbox(Inches(0.8), Inches(7.17), Inches(11.7), Inches(0.3))
        p_foot = tb_foot.text_frame.paragraphs[0]
        p_foot.text = "Cloud Patient Review & Recommendation System with NLP Sentiment Analysis  |  Project Review 2"
        p_foot.font.size = Pt(9)
        p_foot.font.color.rgb = MUTED_GRAY

    # ==================== SLIDE 1: TITLE SLIDE ====================
    s1 = prs.slides.add_slide(blank_layout)
    bg1 = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = PRIMARY_DARK
    bg1.line.fill.background()
    
    badge = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), Inches(1.4), Inches(4.2), Inches(0.45))
    badge.fill.solid()
    badge.fill.fore_color.rgb = TEAL_ACCENT
    badge.line.fill.background()
    tb_b = badge.text_frame.paragraphs[0]
    tb_b.text = "HEALTHCARE AI & NLP CLOUD PLATFORM"
    tb_b.font.size = Pt(11)
    tb_b.font.bold = True
    tb_b.font.color.rgb = WHITE
    tb_b.alignment = PP_ALIGN.CENTER
    
    tb_main = s1.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(11.0), Inches(2.2))
    p_t1 = tb_main.text_frame.paragraphs[0]
    p_t1.text = "Cloud Patient Review &\nDoctor Recommendation System"
    p_t1.font.size = Pt(36)
    p_t1.font.bold = True
    p_t1.font.color.rgb = WHITE
    
    p_t2 = tb_main.text_frame.add_paragraph()
    p_t2.text = "Intelligent Disease & Symptom-Based Specialist Discovery with SBERT NLP Sentiment Analysis"
    p_t2.font.size = Pt(16)
    p_t2.font.color.rgb = RGBColor(148, 163, 184)
    p_t2.space_before = Pt(12)
    
    card = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), Inches(4.8), Inches(11.0), Inches(1.8))
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(15, 30, 58)
    card.line.color.rgb = SKY_BLUE
    card.line.width = Pt(1.5)
    
    tb_card = s1.shapes.add_textbox(Inches(1.5), Inches(4.95), Inches(10.4), Inches(1.5))
    tf_c = tb_card.text_frame
    
    p = tf_c.paragraphs[0]
    p.text = "• Technology Stack: Python (Flask), PostgreSQL 16 (Render Cloud), SBERT & Scikit-Learn NLP, Gunicorn"
    p.font.size = Pt(13)
    p.font.color.rgb = WHITE
    
    p = tf_c.add_paragraph()
    p.text = "• Key Features: 26,712 Doctors Catalogue, Automated Appointment Lifecycle, Anonymized Patient Reviews"
    p.font.size = Pt(13)
    p.font.color.rgb = WHITE
    
    p = tf_c.add_paragraph()
    p.text = "• Deployment: Render Cloud Web Service & Managed Database with Continuous GitHub CI/CD Sync"
    p.font.size = Pt(13)
    p.font.color.rgb = WHITE

    # ==================== SLIDE 2: PROJECT OVERVIEW ====================
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "Project Overview & Problem Statement", "EXECUTIVE SUMMARY")
    
    col_width = Inches(3.64)
    gap = Inches(0.4)
    
    c1 = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), col_width, Inches(5.1))
    c1.fill.solid()
    c1.fill.fore_color.rgb = LIGHT_BG
    c1.line.color.rgb = RGBColor(239, 68, 68)
    c1.line.width = Pt(1.5)
    tb1 = s2.shapes.add_textbox(Inches(1.0), Inches(1.8), col_width - Inches(0.4), Inches(4.7))
    tf1 = tb1.text_frame
    p = tf1.paragraphs[0]
    p.text = "Challenges in Healthcare"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = RGBColor(185, 28, 28)
    
    bullets1 = [
        "Difficulty finding the right specialist for complex or multi-organ symptoms.",
        "Lack of genuine, unbiased patient feedback due to fear of doctor retaliation.",
        "Unreliable ratings in generic directories without appointment verification.",
        "Absence of transparent consultation fees and waiting time insights.",
        "Manual, fragmented booking and appointment tracking across hospitals."
    ]
    for b in bullets1:
        p = tf1.add_paragraph()
        p.text = "• " + b
        p.font.size = Pt(12)
        p.font.color.rgb = SLATE_TEXT
        p.space_before = Pt(8)
        
    c2 = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8) + col_width + gap, Inches(1.6), col_width, Inches(5.1))
    c2.fill.solid()
    c2.fill.fore_color.rgb = LIGHT_BG
    c2.line.color.rgb = TEAL_ACCENT
    c2.line.width = Pt(1.5)
    tb2 = s2.shapes.add_textbox(Inches(1.0) + col_width + gap, Inches(1.8), col_width - Inches(0.4), Inches(4.7))
    tf2 = tb2.text_frame
    p = tf2.paragraphs[0]
    p.text = "Proposed AI Solution"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = TEAL_ACCENT
    
    bullets2 = [
        "NLP Symptom Assessment: Matches user queries to verified specialists using semantic similarity.",
        "Verified Appointment Reviews: Only patients who completed a consultation can review.",
        "Strict Patient Anonymity: Reviewer identity is masked to doctors to preserve healthcare confidentiality.",
        "Automated Sentiment Analysis: NLP categorizes feedback into Positive, Neutral, or Negative.",
        "Complete Doctor Care Portal: Allows doctors to approve, track, and complete appointments."
    ]
    for b in bullets2:
        p = tf2.add_paragraph()
        p.text = "• " + b
        p.font.size = Pt(12)
        p.font.color.rgb = SLATE_TEXT
        p.space_before = Pt(8)
        
    c3 = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8) + (col_width + gap) * 2, Inches(1.6), col_width, Inches(5.1))
    c3.fill.solid()
    c3.fill.fore_color.rgb = LIGHT_BG
    c3.line.color.rgb = SKY_BLUE
    c3.line.width = Pt(1.5)
    tb3 = s2.shapes.add_textbox(Inches(1.0) + (col_width + gap) * 2, Inches(1.8), col_width - Inches(0.4), Inches(4.7))
    tf3 = tb3.text_frame
    p = tf3.paragraphs[0]
    p.text = "Core Objectives"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = SKY_BLUE
    
    bullets3 = [
        "Catalogue 26,712+ doctors across Tamil Nadu with location, fees & ratings.",
        "Sub-second doctor recommendation response using optimized database indexes.",
        "100% cloud-deployed on Render with managed PostgreSQL and automated migrations.",
        "Interactive Admin Dashboard for hospital & doctor onboarding and review moderation.",
        "Robust auto-healing database schema with multi-layer fallback resilience."
    ]
    for b in bullets3:
        p = tf3.add_paragraph()
        p.text = "• " + b
        p.font.size = Pt(12)
        p.font.color.rgb = SLATE_TEXT
        p.space_before = Pt(8)

    # ==================== SLIDE 3: USE CASE DIAGRAM ====================
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "System Use Case Diagram (Actors & Interactions)", "UML ARCHITECTURE")
    s3.shapes.add_picture(img_usecase, Inches(0.8), Inches(1.45), Inches(7.5), Inches(5.35))
    
    side_box = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.5), Inches(1.45), Inches(4.0), Inches(5.35))
    side_box.fill.solid()
    side_box.fill.fore_color.rgb = LIGHT_BG
    side_box.line.color.rgb = TEAL_ACCENT
    side_box.line.width = Pt(1.5)
    
    tb_side = s3.shapes.add_textbox(Inches(8.7), Inches(1.6), Inches(3.6), Inches(5.0))
    tf_s = tb_side.text_frame
    p = tf_s.paragraphs[0]
    p.text = "Key Actor Roles"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_DARK
    
    roles_info = [
        ("Patient Role:", "Searches specialists by symptoms, books consultations, downloads verified appointment letters, and submits anonymous feedback."),
        ("Doctor Role:", "Reviews incoming patient requests, approves visits, records clinical prescriptions, views anonymized feedback, and posts professional responses."),
        ("Administrator Role:", "Oversees hospital listings, verifies doctor profiles, moderates flagged patient reviews, and monitors system audit logs.")
    ]
    for title, desc in roles_info:
        p = tf_s.add_paragraph()
        p.text = title
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = TEAL_ACCENT
        p.space_before = Pt(10)
        
        p = tf_s.add_paragraph()
        p.text = desc
        p.font.size = Pt(11)
        p.font.color.rgb = SLATE_TEXT

    # ==================== SLIDE 4: DFD LEVEL 0 ====================
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "Data Flow Diagram (DFD) - Level 0 (Context Diagram)", "SYSTEM DATA MODEL")
    s4.shapes.add_picture(img_dfd0, Inches(0.8), Inches(1.55), Inches(7.6), Inches(5.2))
    
    side_box = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(1.55), Inches(3.9), Inches(5.2))
    side_box.fill.solid()
    side_box.fill.fore_color.rgb = LIGHT_BG
    side_box.line.color.rgb = SKY_BLUE
    side_box.line.width = Pt(1.5)
    
    tb_side = s4.shapes.add_textbox(Inches(8.8), Inches(1.7), Inches(3.5), Inches(4.8))
    tf_s = tb_side.text_frame
    p = tf_s.paragraphs[0]
    p.text = "Context Flow Analysis"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_DARK
    
    dfd0_notes = [
        ("External Boundary:", "Defines all inputs and outputs interacting with the single central Healthcare AI Portal process (0.0)."),
        ("Patient Input Stream:", "Disease, symptoms, location preference, and consultation feedback enter the system."),
        ("Doctor Input Stream:", "Approval status, diagnosis notes, medical prescriptions, and responses enter the system."),
        ("Admin Input Stream:", "Moderation actions and configuration data enter the system."),
        ("System Output Stream:", "Targeted doctor recommendations, booking letters, and anonymous feedback analytics are dispatched.")
    ]
    for title, desc in dfd0_notes:
        p = tf_s.add_paragraph()
        p.text = "• " + title + " " + desc
        p.font.size = Pt(10.5)
        p.font.color.rgb = SLATE_TEXT
        p.space_before = Pt(7)

    # ==================== SLIDE 5: DFD LEVEL 1 ====================
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "Data Flow Diagram (DFD) - Level 1 (Processes & Data Stores)", "DETAILED PROCESS DECOMPOSITION")
    s5.shapes.add_picture(img_dfd1, Inches(0.8), Inches(1.45), Inches(7.5), Inches(5.4))
    
    side_box = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.5), Inches(1.45), Inches(4.0), Inches(5.4))
    side_box.fill.solid()
    side_box.fill.fore_color.rgb = LIGHT_BG
    side_box.line.color.rgb = TEAL_ACCENT
    side_box.line.width = Pt(1.5)
    
    tb_side = s5.shapes.add_textbox(Inches(8.7), Inches(1.6), Inches(3.6), Inches(5.0))
    tf_s = tb_side.text_frame
    p = tf_s.paragraphs[0]
    p.text = "5 Sub-Processes & Stores"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_DARK
    
    dfd1_notes = [
        ("1.0 Auth & Profile:", "Validates patient & doctor credentials against D1: Patients & D2: Doctors."),
        ("2.0 NLP Recommendation:", "Queries D2 (26,712 doctors) based on symptom similarity, distance, and budget."),
        ("3.0 Appointment Lifecycle:", "Records pending/approved/completed visits in D3: Appointments."),
        ("4.0 NLP Sentiment Engine:", "Analyzes text feedback and writes anonymized rating records into D4: Patient Reviews."),
        ("5.0 Admin & Audit:", "Moderates flagged content and logs critical system actions into D5: Audit Logs.")
    ]
    for title, desc in dfd1_notes:
        p = tf_s.add_paragraph()
        p.text = title
        p.font.size = Pt(11.5)
        p.font.bold = True
        p.font.color.rgb = TEAL_ACCENT
        p.space_before = Pt(6)
        
        p = tf_s.add_paragraph()
        p.text = desc
        p.font.size = Pt(10)
        p.font.color.rgb = SLATE_TEXT

    # ==================== SLIDE 6: SEQUENCE DIAGRAM ====================
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "Sequence Diagram (Consultation & Feedback Lifecycle)", "BEHAVIORAL LIFECYCLE")
    s6.shapes.add_picture(img_seq, Inches(0.8), Inches(1.45), Inches(7.6), Inches(5.4))
    
    side_box = s6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(1.45), Inches(3.9), Inches(5.4))
    side_box.fill.solid()
    side_box.fill.fore_color.rgb = LIGHT_BG
    side_box.line.color.rgb = RGBColor(139, 92, 246)
    side_box.line.width = Pt(1.5)
    
    tb_side = s6.shapes.add_textbox(Inches(8.8), Inches(1.6), Inches(3.5), Inches(5.0))
    tf_s = tb_side.text_frame
    p = tf_s.paragraphs[0]
    p.text = "Step-by-Step Sequence"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_DARK
    
    seq_steps = [
        ("1. Booking Phase:", "Patient books consultation. Appointment created in PostgreSQL with status 'Pending' and unique reference."),
        ("2. Doctor Approval:", "Doctor receives notification, reviews medical symptoms, and approves visit."),
        ("3. Treatment Completion:", "Doctor records treatment completion with clinical prescription and notes."),
        ("4. Patient Review & NLP:", "Patient enters feedback. SBERT/NLP categorizes sentiment (Positive/Neutral/Negative)."),
        ("5. Anonymous Reflection:", "Review is saved with strict privacy masking. Immediately reflected on Doctor Dashboard metrics.")
    ]
    for title, desc in seq_steps:
        p = tf_s.add_paragraph()
        p.text = title
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = RGBColor(124, 58, 237)
        p.space_before = Pt(6)
        
        p = tf_s.add_paragraph()
        p.text = desc
        p.font.size = Pt(9.8)
        p.font.color.rgb = SLATE_TEXT

    # ==================== SLIDE 7: DEPLOYMENT DIAGRAM ====================
    s7 = prs.slides.add_slide(blank_layout)
    add_header(s7, "Cloud Deployment Diagram (Render Cloud Architecture)", "PRODUCTION TOPOLOGY")
    s7.shapes.add_picture(img_deploy, Inches(0.8), Inches(1.45), Inches(7.6), Inches(5.4))
    
    side_box = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(1.45), Inches(3.9), Inches(5.4))
    side_box.fill.solid()
    side_box.fill.fore_color.rgb = LIGHT_BG
    side_box.line.color.rgb = PRIMARY_DARK
    side_box.line.width = Pt(1.5)
    
    tb_side = s7.shapes.add_textbox(Inches(8.8), Inches(1.6), Inches(3.5), Inches(5.0))
    tf_s = tb_side.text_frame
    p = tf_s.paragraphs[0]
    p.text = "Cloud Infrastructure"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = PRIMARY_DARK
    
    deploy_notes = [
        ("Render Web Service:", "Hosts Python 3.11 environment with Gunicorn WSGI (2 workers) serving Flask MVC application and NLP modules."),
        ("Managed PostgreSQL:", "Hosted in Render private cloud network with automatic backups, connection pooling, and SSL encryption."),
        ("GitHub CI/CD Automation:", "Every commit pushed to origin/main automatically triggers zero-downtime build and redeployment."),
        ("Edge SSL Termination:", "Full end-to-end HTTPS encryption through Cloudflare/Render edge gateway.")
    ]
    for title, desc in deploy_notes:
        p = tf_s.add_paragraph()
        p.text = title
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = TEAL_ACCENT
        p.space_before = Pt(6)
        
        p = tf_s.add_paragraph()
        p.text = desc
        p.font.size = Pt(9.8)
        p.font.color.rgb = SLATE_TEXT

    # ==================== SLIDE 8: CORE INNOVATIONS & PRIVACY ====================
    s8 = prs.slides.add_slide(blank_layout)
    add_header(s8, "Key Innovations, Security & Privacy Safeguards", "TECHNICAL HIGHLIGHTS")
    
    card_w = Inches(5.6)
    card_h = Inches(2.35)
    
    cards_data = [
        ("Strict Patient Privacy Guarantee", [
            "Submitter identity (name and email) is cryptographically masked when displayed to doctors.",
            "Doctor sees verified badges (e.g. 'Verified Patient #EFA5C0') ensuring honest reviews without fear of discrimination.",
            "Full reviewer email is preserved strictly for administrator audit logs."
        ], Inches(0.8), Inches(1.6), TEAL_ACCENT),
        ("Real-time NLP Sentiment Analysis", [
            "Trained NLP pipeline categorizes text into Positive, Neutral, or Negative sentiment.",
            "NLP feature extractor automatically identifies hospital waiting time issues, bedside manner, and cost concerns.",
            "Aggregates satisfaction scores dynamically on Doctor Care Portal."
        ], Inches(6.9), Inches(1.6), SKY_BLUE),
        ("Cloud Auto-Healing Database Architecture", [
            "Automatic schema reconciliation ensures missing columns or sequences are healed on-the-fly.",
            "Idempotent review upsert prevents duplicate review submissions per appointment.",
            "High-speed multi-row batch inserts for 26,712 doctor records in under 3 seconds."
        ], Inches(0.8), Inches(4.3), RGBColor(139, 92, 246)),
        ("High-Performance Matching & Caching", [
            "Normalized doctor matching strips titles ('Dr.', 'DR.') and punctuation for 100% match accuracy.",
            "Multi-criteria filtering combines disease specialization, consultation fee budget, and district location.",
            "Graceful fallback mechanism ensures zero downtime even during database maintenance."
        ], Inches(6.9), Inches(4.3), RGBColor(16, 185, 129))
    ]
    
    for title, bullets, x, y, border_col in cards_data:
        box = s8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_w, card_h)
        box.fill.solid()
        box.fill.fore_color.rgb = LIGHT_BG
        box.line.color.rgb = border_col
        box.line.width = Pt(1.5)
        
        tb = s8.shapes.add_textbox(x + Inches(0.2), y + Inches(0.15), card_w - Inches(0.4), card_h - Inches(0.3))
        tf = tb.text_frame
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(13.5)
        p.font.bold = True
        p.font.color.rgb = border_col
        
        for b in bullets:
            p = tf.add_paragraph()
            p.text = "• " + b
            p.font.size = Pt(10.5)
            p.font.color.rgb = SLATE_TEXT
            p.space_before = Pt(4)

    # ==================== SLIDE 9: CONCLUSION & FUTURE WORK ====================
    s9 = prs.slides.add_slide(blank_layout)
    add_header(s9, "Conclusion & Future Enhancements", "PROJECT WRAP-UP")
    
    box_l = s9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.1))
    box_l.fill.solid()
    box_l.fill.fore_color.rgb = LIGHT_BG
    box_l.line.color.rgb = TEAL_ACCENT
    box_l.line.width = Pt(1.5)
    
    tb_l = s9.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(5.2), Inches(4.7))
    tf_l = tb_l.text_frame
    p = tf_l.paragraphs[0]
    p.text = "Completed Project Milestones"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = TEAL_ACCENT
    
    achievements = [
        "End-to-End Functional Cloud System deployed live on Render Cloud.",
        "Integrated 26,712 verified doctor dataset covering all 38 districts of Tamil Nadu.",
        "Accurate NLP sentiment classification for consultation reviews.",
        "Complete Doctor Care Portal with real-time feedback and metrics dashboard.",
        "Patient appointment booking, printable verification letters, and review lifecycle.",
        "Full role-based security (Patient, Doctor, Admin) with privacy masking."
    ]
    for a in achievements:
        p = tf_l.add_paragraph()
        p.text = "✅ " + a
        p.font.size = Pt(11.5)
        p.font.color.rgb = SLATE_TEXT
        p.space_before = Pt(8)
        
    box_r = s9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.9), Inches(1.6), Inches(5.6), Inches(5.1))
    box_r.fill.solid()
    box_r.fill.fore_color.rgb = LIGHT_BG
    box_r.line.color.rgb = SKY_BLUE
    box_r.line.width = Pt(1.5)
    
    tb_r = s9.shapes.add_textbox(Inches(7.1), Inches(1.8), Inches(5.2), Inches(4.7))
    tf_r = tb_r.text_frame
    p = tf_r.paragraphs[0]
    p.text = "Future Roadmap"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = SKY_BLUE
    
    future = [
        "Tele-Medicine Integration: In-app video consultations using WebRTC.",
        "Multi-lingual Voice Queries: Voice recognition supporting Tamil and English.",
        "IoT Vital Signs Sync: Connecting wearable health bands for real-time monitoring.",
        "Native Mobile Applications: Flutter-based Android and iOS client apps.",
        "Automated Prescription Delivery: Direct integration with hospital e-pharmacies."
    ]
    for f in future:
        p = tf_r.add_paragraph()
        p.text = "🚀 " + f
        p.font.size = Pt(11.5)
        p.font.color.rgb = SLATE_TEXT
        p.space_before = Pt(8)

    # Save presentation
    ppt_path = os.path.join(os.getcwd(), "Healthcare_AI_Project_Presentation.pptx")
    prs.save(ppt_path)
    print("[SUCCESS] Presentation generated successfully: Healthcare_AI_Project_Presentation.pptx")
    return ppt_path

if __name__ == '__main__':
    p1, p2, p3, p4, p5 = generate_diagrams()
    build_presentation(p1, p2, p3, p4, p5)

