# 📸 Student Photo Import Guide

## Quick Start: Interactive Bulk Matcher

### Overview
Upload a ZIP of student photos and match them interactively with visual preview before saving.

---

## Step-by-Step Workflow

### 1️⃣ Prepare Your Photos
- Collect all student photos in one folder
- Photos should be PNG, JPG, or JPEG format
- Any filenames work (they'll be renamed automatically)
- Compress the folder into a ZIP file

**Example folder structure:**
```
student_photos/
├── IMG_001.jpg
├── IMG_002.jpg
├── IMG_003.jpg
├── photo_4.png
└── student_5.jpeg
```

**Tip:** Name photos in order if possible (001, 002, 003...) for easier matching

---

### 2️⃣ Access the Tool
1. Open your app: `streamlit run home.py`
2. Navigate to **Saved Exams** page
3. Scroll down to find **🔄 Interactive Bulk Photo Matcher**

---

### 3️⃣ Select Student List
**Step 1 in the UI:**
- **Select Exam**: Choose which exam contains your students
- **Filter by Class**: (Optional) Select specific class or choose "All Classes"

This determines which students will be available for matching.

---

### 4️⃣ Upload Photos
**Step 2 in the UI:**
- Click **"Upload ZIP of images"**
- Select your ZIP file
- **OPTIONAL: Upload Order List (CSV/Excel)**
  - Simple file with just Name and Adm No columns
  - **No "Filename" column needed!**
  - Row order = Photo order (1st row → 1st photo)
- Click **"🔍 Load & Auto-Match"** button

The system will:
- Extract all images from ZIP
- If order list uploaded: Match photos to students in exact row order from list
- If no order list: Load students from exam/class, match by selected sort order
- Display preview of all matches

**Order List Example (CSV or Excel):**
```csv
Name,Adm No
John Doe,12345
Jane Smith,12346
Bob Johnson,12347
Alice Brown,12348
```
This matches: 1st photo → John Doe, 2nd photo → Jane Smith, etc.

**Why Use Order List?**
- You have students arranged in a specific order (class register, seating chart)
- Photos taken in that exact order
- No need to worry about sorting—just follow your list
- Faster than matching by name or admission number

---

### 5️⃣ Review & Edit Matching

**Step 3 in the UI:**

**If you uploaded an order list:**
- System shows: "📋 Using uploaded order list"
- Photos matched in exact row order from your list
- Sorting options disabled (your list defines the order)
- You can still manually edit any assignments if needed

**If you didn't upload an order list:**
- System uses exam/class data
- You'll see sorting options

You'll see a table showing:
- **Image preview** (80px thumbnail)
- **Original filename**
- **Student Name** (dropdown to change)
- **Adm No** (auto-filled when name selected)

**Sorting Options (when NOT using order list):**
Choose how to sort the student list before matching:
- **Order in Exam** (default) - matches photos to students as they appear in exam data
- **Name (A-Z)** - sorts students alphabetically, useful if photos are sorted by name
- **Adm No** - sorts by admission number, useful if photos follow admission order

**Re-matching (when NOT using order list):**
- Change sort order
- Click **"🔄 Re-match with current sort"**
- System will reassign photos based on new student order

**Manual Edits (available always):**
- Click any student name dropdown to change assignment
- Adm No auto-updates when you select a name
- Make sure each photo is assigned to correct student

---

### 6️⃣ Save Photos
**Step 4 in the UI:**

Review summary:
- ✅ **X matched** - photos assigned to students
- ⚠️ **X unmatched** - photos not assigned (will be skipped)

Options:
- ☑️ **Overwrite existing photos** - replace if student already has a photo
- ☐ Uncheck to keep existing photos

Click **"💾 Save All Matched Photos"**

The system will:
- Save each matched photo
- Rename files to standardized format
- Update mapping database
- Show success count

---

## Tips & Best Practices

### Matching Strategies

**Strategy 1: Order List (RECOMMENDED for specific order)**
Perfect when you have photos in a specific, predetermined order:
1. Create CSV/Excel with Name and Adm No columns
2. List students in exact order you want (matches photo order)
3. Upload order list + ZIP
4. Click "Load & Auto-Match"
5. System matches: 1st photo → 1st row, 2nd photo → 2nd row, etc.
6. Verify and save

**When to use:**
- Photos taken following class register order
- Photos organized by seating arrangement
- Pre-planned photo order (alphabetical, by ID, custom)
- You have a master list and want exact matching

**Strategy 2: Auto-Sort with Exam Data**
If your photos are already in order (numbered, alphabetically, etc.):
1. Don't upload order list
2. Select appropriate sort order in Step 3
3. Click "Load & Auto-Match"
4. Verify matches are correct
5. Save immediately

**Strategy 3: Manual Assignment**
If photos are randomly ordered:
1. Load all photos (no order list)
2. Review each preview
3. Manually select correct student from dropdown
4. Save when all verified

---

## Common Workflows

### Workflow A: Using Order List (Register Order)
You have a class register and took photos in that order:
1. Export class register to CSV (Name, Adm No columns)
2. Take photos in exact register order
3. ZIP all photos
4. Select exam and class
5. Upload ZIP + CSV order list
6. Click "Load & Auto-Match"
7. Perfect 1:1 match—verify and save!

### Workflow B: Using Order List (Custom Order)
You arranged students in custom order and took photos:
1. Create your own list in Excel/CSV (any order you want)
2. Take photos following that list order
3. ZIP photos
4. Upload ZIP + your custom list
5. System matches exactly as you planned
6. Save immediately

### Workflow C: Alphabetical with Auto-Sort
Photos organized alphabetically by surname:
1. Don't upload order list
2. Select exam and class
3. Upload ZIP (photos named by surname or numbered)
4. Choose "Name (A-Z)" sort
5. Auto-match aligns with alphabetical order
6. Verify and save

### Workflow D: Admission Number Order
Photos collected by admission number order:
1. Don't upload order list
2. Select exam and class
3. Upload ZIP
4. Choose "Adm No" sort
5. Auto-match aligns perfectly
6. Verify and save

### Workflow E: Random/Mixed Photos
Photos from various sources, no particular order:
1. Don't upload order list
2. Select exam and class
3. Upload ZIP
4. Leave default sort
5. Manually review each photo preview
6. Use dropdown to assign correct student
7. Take your time—accuracy matters!
8. Save when confident

---

## After Import

### Verify Photos Saved
1. Go to single photo upload section
2. Select exam and student
3. Check if photo appears in preview
4. Photo should show correctly

### Use in Report Cards
1. Navigate to **Report Cards** page
2. Ensure **"Include Student Photo"** is checked in settings
3. Generate report cards
4. Photos appear next to Student Info table

### View in Student History
1. Go to **Student History** page
2. Search for student
3. Photo displays next to performance metrics

---

## Troubleshooting

### Photos Not Loading
- **Issue**: ZIP upload fails
- **Solution**: Ensure ZIP is not corrupted; try re-zipping folder

### Wrong Auto-Match
- **Issue**: Photos matched to wrong students
- **Solution**: Change sort order and re-match, or manually edit each assignment

### Some Students Missing
- **Issue**: Fewer students than photos
- **Solution**: Extra photos will show as "unmatched" and won't be saved (this is normal)

### Photos Blurry in Report
- **Issue**: Low quality in report cards
- **Solution**: Upload higher resolution originals; system resizes to max 512px

### Cannot Overwrite
- **Issue**: New photo not replacing old
- **Solution**: Check "Overwrite existing photos" checkbox before saving

---

## Advanced: CSV-Based Import

For automation or if you have a pre-made mapping file:

### Steps:
1. Generate template CSV: **"Generate Class Photo Template"**
2. Download template (Name, Adm No, Filename columns)
3. Fill "Filename" column with exact image filenames
4. Save CSV
5. Upload ZIP + CSV in "Advanced: CSV-Based Bulk Import" section
6. Click "Process Bulk Import"

**Use cases:**
- Integrating with external student database
- Scripted/automated photo imports
- When you have a pre-existing mapping spreadsheet

---

## Storage Information

### Where Photos Are Saved
```
saved_exams_storage/
├── student_photos/
│   ├── 12345.png          (Adm No based filename)
│   ├── 67890.jpg
│   └── abc123def456.png   (Hash-based if no Adm No)
└── student_photos.json    (Mapping database)
```

### Mapping File Structure
```json
{
  "12345": {
    "path": "...\\student_photos\\12345.png",
    "name": "John Doe",
    "adm_no": "12345",
    "updated_at": "2025-11-10 14:30:00"
  }
}
```

---

## Support

**Issues or Questions?**
- Contact: Munyua Kamau
- Phone: 0793975959

---

**Enjoy seamless photo management!** 📸✨
