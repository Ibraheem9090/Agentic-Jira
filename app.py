import os
import re
import tempfile
import subprocess
import hashlib
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI

# 1. Page Configuration
st.set_page_config(
    page_title="Jira AI Test Generator",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Styling for enterprise look
st.markdown("""
    <style>
    .main { background-color: #0f172a; color: #f1f5f9; }
    .stTextInput input, .stTextArea textarea {
        background-color: #0f172a !important;
        color: #f1f5f9 !important;
        border: 1px solid #475569 !important;
        border-radius: 6px;
    }
    .stButton button {
        background-color: #2563eb !important;
        color: white !important;
        font-weight: bold;
        border-radius: 6px;
        border: none;
    }
    .stButton button:hover {
        background-color: #3b82f6 !important;
    }
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid #1e293b;
        padding-bottom: 16px;
        margin-bottom: 24px;
    }
    </style>
""", unsafe_allow_html=True)

# 2. Retrieve API Key securely from Streamlit Secrets or Environment Variables
api_key = st.secrets.get("NVIDIA_API_KEY") or os.getenv("NVIDIA_API_KEY")

if not api_key:
    st.error("Missing NVIDIA_API_KEY! Please configure it in .streamlit/secrets.toml or your environment variables.")
    st.stop()

# Ensure raw key format (strip accidental 'Bearer ' prefix if passed via secrets)
clean_api_key = api_key.replace("Bearer ", "").strip()

MODEL_NAME = "moonshotai/kimi-k3"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=clean_api_key
)

def clean_code(raw_text: str) -> str:
    code_block_match = re.search(r'```(?:jsx|tsx|javascript|typescript|js)?\s*([\s\S]*?)```', raw_text, re.IGNORECASE)
    if code_block_match:
        raw_text = code_block_match.group(1)

    cleaned = raw_text.replace('```', '').strip()
    return cleaned.strip()

def generate_llm_response(prompt: str, system_prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1500,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"// Error communicating with NVIDIA API: {str(e)}"

def run_vitest(component_code: str, test_code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        with open(os.path.join(temp_dir, "App.jsx"), "w", encoding="utf-8") as f:
            f.write(component_code)
        with open(os.path.join(temp_dir, "App.test.jsx"), "w", encoding="utf-8") as f:
            f.write(test_code)
        with open(os.path.join(temp_dir, "vite.config.js"), "w", encoding="utf-8") as f:
            f.write("""
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  test: { globals: true, environment: 'jsdom' }
});
""")
        env = os.environ.copy()
        try:
            env["NODE_PATH"] = subprocess.check_output(["npm", "root", "-g"]).decode().strip()
        except Exception:
            pass

        try:
            res = subprocess.run(
                ["npx", "--yes", "vitest", "run", "--dir", temp_dir],
                capture_output=True, text=True, timeout=30, shell=True, env=env
            )
            passed = (res.returncode == 0)
            output = res.stdout if passed else res.stdout + "\n" + res.stderr
            return passed, output
        except Exception as e:
            return False, f"Vitest Execution Error: {str(e)}"

def build_preview(component_code: str) -> str:
    # Sanitize code for browser Babel evaluation (strip ES module imports/exports)
    sanitized_code = re.sub(r'import\s+.*?;', '', component_code)
    sanitized_code = re.sub(r'export\s+default\s+function\s+', 'function ', sanitized_code)
    sanitized_code = re.sub(r'export\s+default\s+', '', sanitized_code)
    sanitized_code = re.sub(r'export\s+', '', sanitized_code)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <script src="[https://unpkg.com/react@18/umd/react.development.js](https://unpkg.com/react@18/umd/react.development.js)"></script>
    <script src="[https://unpkg.com/react-dom@18/umd/react-dom.development.js](https://unpkg.com/react-dom@18/umd/react-dom.development.js)"></script>
    <script src="[https://unpkg.com/@babel/standalone/babel.min.js](https://unpkg.com/@babel/standalone/babel.min.js)"></script>
    <script src="[https://cdn.tailwindcss.com](https://cdn.tailwindcss.com)"></script>
    <style>
        body {{ background-color: #020617; color: #f8fafc; font-family: system-ui, sans-serif; padding: 16px; margin: 0; }}
        #root {{ background: #1e293b; border: 1px solid #334155; padding: 20px; border-radius: 8px; min-height: 250px; }}
        .error-box {{ color: #f87171; background: #450a0a; border: 1px solid #991b1b; padding: 12px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; font-size: 12px; }}
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel" data-presets="react,typescript">
        const {{ useState, useEffect, useCallback, useMemo, useRef, useReducer }} = React;

        window.addEventListener('error', function(e) {{
            document.getElementById('root').innerHTML = '<div class="error-box">Runtime Error: ' + e.message + '</div>';
        }});

        try {{
            {sanitized_code}

            if (typeof App !== 'undefined') {{
                const root = ReactDOM.createRoot(document.getElementById('root'));
                root.render(<App/>);
            }} else {{
                document.getElementById('root').innerHTML = '<div class="error-box">Error: Component "App" was not found in generated code.</div>';
            }}
        }} catch (err) {{
            document.getElementById('root').innerHTML = '<div class="error-box">Compilation Error: ' + err.message + '</div>';
        }}
    </script>
</body>
</html>"""

# 3. Main Dashboard UI Layout
st.markdown("""
    <div class="header-container">
        <h1 style="font-size: 24px; font-weight: bold; color: #60a5fa; margin: 0;">Jira AI Test Generator</h1>
        <span style="font-size: 14px; font-weight: 600; color: #94a3b8;">Designed & Developed by <span style="color: #93c5fd;">Aafreen Shaikh</span></span>
    </div>
""", unsafe_allow_html=True)

# Input Card Container
with st.container():
    summary_input = st.text_input("Jira Summary", value="Build a status badge component with interface definitions")
    desc_input = st.text_area("Jira Description", value="Component must feature explicit interface/type definitions, class or functional structure, state management, and toggle behavior.")
    run_button = st.button("Run Pipeline")

# Default component for initial page load
DEFAULT_CODE = """function App() {
  const [status, setStatus] = React.useState("Active");
  return (
    <div className="p-4 bg-slate-900 rounded-lg text-white space-y-4">
      <h3 className="text-sky-400 font-semibold">Interactive Component Simulation</h3>
      <p className="text-slate-400 text-sm">Live rendered via secure internal sandbox (Powered by NVIDIA NIM).</p>
      <button 
        onClick={() => setStatus(status === "Active" ? "Inactive" : "Active")}
        className={`px-4 py-2 rounded-full font-bold transition-all ${
          status === 'Active' ? 'bg-green-500 text-white' : 'bg-yellow-500 text-slate-900'
        }`}
      >
        Status: {status} (Click to Toggle)
      </button>
    </div>
  );
}"""

# Session state initialization
if "code_output" not in st.session_state:
    st.session_state.code_output = DEFAULT_CODE
if "test_output" not in st.session_state:
    st.session_state.test_output = "// Vitest cases will appear here..."
if "preview_html" not in st.session_state:
    st.session_state.preview_html = build_preview(DEFAULT_CODE)

if run_button:
    status_box = st.status("Starting pipeline execution...", expanded=True)
    
    try:
        # Stage 1: Component Generation
        status_box.update(label="Stage 1: Generating Component & Interfaces via NVIDIA API...", state="running")
        prompt_comp = f"Write a complete functional React component named App for: {summary_input}. Description: {desc_input}. Do not import external icon libraries."
        raw_code = generate_llm_response(prompt_comp, "You are an expert enterprise React developer. Always name the main component App. Output ONLY executable code enclosed in a markdown code block.")
        comp_code = clean_code(raw_code)
        st.session_state.code_output = comp_code
        status_box.write("✓ Stage 1 Complete: Component generated!")

        # Stage 2: Test Case Generation
        status_box.update(label="Stage 2: Writing Vitest Test Cases...", state="running")
        test_prompt = f"Write comprehensive Vitest unit tests using @testing-library/react for this React component code:\n\n{comp_code}"
        raw_test = generate_llm_response(test_prompt, "You are a senior React QA engineer. Write robust unit test cases using Vitest and React Testing Library matching the component structure. Output ONLY executable code in a markdown block.")
        test_code = clean_code(raw_test)
        st.session_state.test_output = test_code
        status_box.write("✓ Stage 2 Complete: Test cases generated!")

        # Stage 3: Vitest Execution
        status_box.update(label="Stage 3: Running Vitest Test Suite...", state="running")
        passed, out = run_vitest(comp_code, test_code)
        status_box.write(f"✓ Stage 3 Complete (Vitest Passed: {passed})")

        # Stage 4: Live Preview
        status_box.update(label="Stage 4: Rendering Live UI Preview...", state="running")
        st.session_state.preview_html = build_preview(comp_code)
        status_box.write("✓ Pipeline Finished Successfully!")
        
        status_box.update(label="Pipeline Execution Complete!", state="complete", expanded=False)
        st.rerun()

    except Exception as e:
        status_box.update(label=f"Pipeline Failed: {str(e)}", state="error")

# 4. Result Dashboard Panes (2-Column Grid Layout)
col1, col2 = st.columns(2)

with col1:
    st.markdown("<h3 style='color: #4ade80; font-size: 14px;'>React Component & Interface Code</h3>", unsafe_allow_html=True)
    st.code(st.session_state.code_output, language="javascript")
    
    st.markdown("<h3 style='color: #facc15; font-size: 14px;'>Vitest Test Cases</h3>", unsafe_allow_html=True)
    st.code(st.session_state.test_output, language="javascript")

with col2:
    st.markdown("<h3 style='color: #c084fc; font-size: 14px;'>Live Component Preview</h3>", unsafe_allow_html=True)
    # Generate unique key per code hash to force Streamlit iframe reset on code update
    code_hash = hashlib.md5(st.session_state.code_output.encode()).hexdigest()
    components.html(st.session_state.preview_html, height=520, scrolling=True)
