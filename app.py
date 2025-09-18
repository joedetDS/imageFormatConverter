import streamlit as st
from PIL import Image, ImageSequence, UnidentifiedImageError
import io
import os
import zipfile
from typing import List, Tuple

# ------------------------
# App configuration & styles
# ------------------------
APP_NAME = "FormatForge — Instant Image Alchemist"

def set_page_config():
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="🪄",
        layout="centered",
        initial_sidebar_state="auto",
    )
    st.markdown(
        """
        <style>
        .header { display:flex; align-items:center; gap:0.75rem; }
        .brand { font-size:26px; font-weight:700; color:#0f4c81; }
        .subtitle { color:#666; margin-top:-6px; font-size:13px; }
        .card { background: linear-gradient(180deg,#ffffff 0%, #f7fbff 100%); padding:18px; border-radius:12px;
                box-shadow: 0 6px 18px rgba(12,31,64,0.06); border: 1px solid rgba(15,76,129,0.06); }
        .small { font-size:13px; color:#444; }
        .muted { color:#6b7280; font-size:13px; }
        .pill { background:#eef2ff; padding:6px 10px; border-radius:999px; font-weight:600; color:#0f4c81; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ------------------------
# Utilities
# ------------------------
def normalize_format_name(name: str) -> str:
    if not name:
        return ""
    name = name.strip().lower()
    mapping = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "ico": "ICO",
        "icon": "ICO",
        "gif": "GIF",
        "bmp": "BMP",
        "webp": "WEBP",
        "tiff": "TIFF",
        "tif": "TIFF",
    }
    return mapping.get(name, name.upper())

def get_extension_for_format(format_name: str) -> str:
    fmt = normalize_format_name(format_name)
    ext_map = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "ICO": ".ico",
        "GIF": ".gif",
        "BMP": ".bmp",
        "WEBP": ".webp",
        "TIFF": ".tiff",
    }
    return ext_map.get(fmt, f".{fmt.lower()}")

def read_image_from_upload(uploaded_file) -> Image.Image:
    uploaded_file.seek(0)
    image_bytes = uploaded_file.read()
    buf = io.BytesIO(image_bytes)
    img = Image.open(buf)
    img.load()
    # keep original bytes available via uploaded_file
    return img

def image_format_from_pil(img: Image.Image, filename_hint: str = "") -> str:
    fmt = getattr(img, "format", None)
    if fmt:
        return fmt.upper()
    # fallback to filename extension
    if filename_hint:
        ext = os.path.splitext(filename_hint)[1].lstrip(".").upper()
        if ext:
            return ext
    # fallback to mode
    return img.mode.upper()

def parse_custom_sizes(text: str) -> List[Tuple[int,int]]:
    """Parse comma-separated sizes like '16,32,48' into list of tuples."""
    try:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        sizes = []
        for p in parts:
            val = int(p)
            if val > 0:
                sizes.append((val, val))
        return sizes
    except Exception:
        return []

def convert_image_to_bytes(
    img: Image.Image,
    target_format: str,
    original_filename: str,
    jpeg_bg_rgb: Tuple[int,int,int] = (255,255,255),
    ico_sizes: List[Tuple[int,int]] = None,
    preserve_animation: bool = True
) -> (bytes, str):
    target = normalize_format_name(target_format)
    out_buffer = io.BytesIO()
    save_kwargs = {}
    img_to_save = img

    # Handle JPEG background if needed
    if target == "JPEG":
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            # composite onto background color
            bg = Image.new("RGB", img.size, jpeg_bg_rgb)
            # If alpha present, use it as mask
            if img.mode in ("RGBA", "LA"):
                bg.paste(img, mask=img.split()[-1])
            else:
                try:
                    bg.paste(img)
                except Exception:
                    bg.paste(img.convert("RGB"))
            img_to_save = bg
        else:
            img_to_save = img.convert("RGB")
    else:
        img_to_save = img

    # ICO: include sizes parameter
    if target == "ICO":
        if ico_sizes:
            save_kwargs["sizes"] = ico_sizes

    # GIF animation preservation
    if target == "GIF" and getattr(img, "is_animated", False) and preserve_animation:
        frames = []
        duration = img.info.get("duration", 100)
        loop = img.info.get("loop", 0)
        try:
            for frame in ImageSequence.Iterator(img):
                # convert frames to palette if needed
                frames.append(frame.convert("RGBA"))
            frames[0].save(out_buffer, format="GIF", save_all=True, append_images=frames[1:], loop=loop, duration=duration, disposal=2)
        except Exception:
            img_to_save.convert("RGBA").save(out_buffer, format="GIF")
    else:
        # Regular save
        # Some formats require conversion; Pillow handles many automatically
        # Use a try/except to catch unsupported format errors.
        try:
            img_to_save.save(out_buffer, format=target, **save_kwargs)
        except Exception as e:
            # fallback: convert to PNG then attempt to save
            temp = img_to_save.convert("RGBA")
            temp.save(out_buffer, format=target if target != "ICO" else "PNG", **save_kwargs)

    out_buffer.seek(0)
    out_bytes = out_buffer.read()
    base_name, _ = os.path.splitext(os.path.basename(original_filename))
    out_filename = f"{base_name}{get_extension_for_format(target)}"
    return out_bytes, out_filename

def make_zip_bytes(files: List[Tuple[bytes,str]]) -> (bytes, str):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for content, filename in files:
            zf.writestr(filename, content)
    buf.seek(0)
    return buf.read(), "converted_images.zip"

# ------------------------
# UI parts
# ------------------------
def sidebar_instructions():
    st.sidebar.markdown("### Instructions")
    st.sidebar.markdown(
        """
        - Upload one or more image files.
        - Choose the format you *think* each file is (we validate automatically).
        - Choose the desired output format.
        - For ICO: choose a preset or specify custom sizes.
        - For JPEG: choose a background color to composite transparent regions.
        - Click **Convert**. Each valid converted file will be listed with a preview and a download button. You can download a ZIP of all converted files.
        """
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown("Supported: PNG, JPG/JPEG, ICO, GIF, BMP, WEBP, TIFF. Animated GIFs preserved when converting to GIF.")

def format_dropdowns(available_choices):
    col1, col2 = st.columns([1,1])
    with col1:
        have_fmt = st.selectbox("I have (select input format)", available_choices, index=0, help="Select the format you think this file is.")
    with col2:
        want_fmt = st.selectbox("Convert to (select output format)", available_choices, index=1, help="Choose the format to convert into.")
    return have_fmt, want_fmt

def show_preview_and_download_single(img_preview_bytes: bytes, caption: str, out_filename: str, mime: str):
    st.image(img_preview_bytes, caption=caption, use_column_width=True)
    st.download_button(label="Download", data=img_preview_bytes, file_name=out_filename, mime=mime)

# ------------------------
# Main app flow
# ------------------------
def main():
    set_page_config()
    sidebar_instructions()

    st.markdown(f"<div class='header'><div class='brand'>🪄 {APP_NAME}</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>Batch image conversion with validation, ICO presets, JPEG transparency handling, and Docker support.</div>", unsafe_allow_html=True)
    st.markdown("<br>")

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("#### Upload & Convert", unsafe_allow_html=True)

    available_choices = ["PNG", "JPG", "JPEG", "ICO", "GIF", "BMP", "WEBP", "TIFF"]

    uploaded_files = st.file_uploader("Choose one or more image files", type=None, accept_multiple_files=True)
    have_fmt, want_fmt = format_dropdowns(available_choices)

    st.markdown("---")
    st.markdown("**Advanced options**")
    col_a, col_b = st.columns([1,1])
    with col_a:
        force_convert = st.checkbox("Force convert even if detected format doesn't match 'I have'", value=False, help="If unchecked, files whose detected formats don't match your 'I have' selection will be skipped.")
        preserve_animation = st.checkbox("Preserve GIF animation when converting to GIF", value=True)
    with col_b:
        jpeg_bg_color = st.color_picker("JPEG background color (used when compositing transparency)", value="#FFFFFF")
        st.caption("Pick a background color for places that were transparent (applies only when converting to JPEG).")

    # ICO presets
    st.markdown("---")
    st.markdown("**ICO presets**")
    ico_preset = st.selectbox("Choose ICO preset (applies only when converting to ICO)", ["Default (16,32,48,64,128,256)", "Small (16,32)", "Medium (64,128)", "Large (256)", "All (256,128,64,48,32,16)", "Custom (comma separated)"])
    custom_sizes_text = ""
    if ico_preset == "Custom (comma separated)":
        custom_sizes_text = st.text_input("Enter sizes (e.g. 16,32,48,64)", value="16,32,48,64")

    convert_clicked = st.button("Convert files", type="primary")

    info_placeholder = st.empty()

    if not uploaded_files:
        st.info("Upload images (single or multiple), choose formats and options, then click Convert.")
    else:
        st.markdown(f"Uploaded {len(uploaded_files)} file(s).")

    if convert_clicked and uploaded_files:
        converted_files = []  # list of tuples (bytes, filename)
        skipped_files = []
        errors = []
        jpeg_rgb = tuple(int(jpeg_bg_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

        # prepare ICO sizes list
        if ico_preset.startswith("Default") or ico_preset.startswith("All"):
            ico_sizes = [(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]
        elif ico_preset.startswith("Small"):
            ico_sizes = [(16,16),(32,32)]
        elif ico_preset.startswith("Medium"):
            ico_sizes = [(64,64),(128,128)]
        elif ico_preset.startswith("Large"):
            ico_sizes = [(256,256)]
        elif ico_preset.startswith("Custom"):
            parsed = parse_custom_sizes(custom_sizes_text or "")
            ico_sizes = parsed if parsed else [(256,256),(128,128),(64,64)]
        else:
            ico_sizes = [(256,256),(128,128),(64,64)]

        for up in uploaded_files:
            try:
                try:
                    img = read_image_from_upload(up)
                except UnidentifiedImageError:
                    # not an image — skip
                    skipped_files.append((up.name, "Unidentified image"))
                    continue

                detected_format = image_format_from_pil(img, up.name)
                selected_input = normalize_format_name(have_fmt)
                detected_norm = normalize_format_name(detected_format)

                if (selected_input != detected_norm) and (not force_convert):
                    skipped_files.append((up.name, f"Format mismatch (detected: {detected_norm})"))
                    continue

                # convert
                out_bytes, out_filename = convert_image_to_bytes(
                    img,
                    want_fmt,
                    up.name,
                    jpeg_bg_rgb=jpeg_rgb,
                    ico_sizes=ico_sizes,
                    preserve_animation=preserve_animation
                )
                converted_files.append((out_bytes, out_filename, detected_norm))
            except Exception as e:
                errors.append((up.name, str(e)))

        # Results
        st.markdown("### Results")
        if converted_files:
            st.success(f"Converted {len(converted_files)} file(s).")
            # Show previews in rows of 2
            for i, (content, filename, detected_norm) in enumerate(converted_files):
                with st.expander(f"{filename} — detected as {detected_norm}", expanded=(i<3)):
                    # show preview (limit large files)
                    try:
                        show_preview_and_download_single(content, caption=f"{filename}", out_filename=filename, mime=f"image/{normalize_format_name(want_fmt).lower()}")
                    except Exception:
                        # fallback to original preview if converted not displayable
                        st.write("Preview not available for this format; download below.")
                        st.download_button("Download", data=content, file_name=filename, mime="application/octet-stream")

            # Single ZIP for batch
            if len(converted_files) > 1:
                zip_bytes, zip_name = make_zip_bytes([(b, fname) for b, fname, _ in [(c,f,d) for (c,f,d) in converted_files]])
                st.download_button("Download all converted files (ZIP)", data=zip_bytes, file_name=zip_name, mime="application/zip")
        else:
            st.info("No files were converted.")

        if skipped_files:
            st.warning("Some files were skipped:")
            for fname, reason in skipped_files:
                st.write(f"- **{fname}** — {reason}")

        if errors:
            st.error("Errors occurred for some files:")
            for fname, err in errors:
                st.write(f"- **{fname}** — {err}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>")
    st.markdown("<div class='small'>Tip: For ICO output, upload a square high-res image (>=256×256). For JPEG, choose a background color that looks good behind transparent areas.</div>", unsafe_allow_html=True)
    st.markdown("<br>")
    st.markdown("**Docker**: use the included `Dockerfile` to build and run a containerized version of this app (see below).")

if __name__ == "__main__":
    main()
