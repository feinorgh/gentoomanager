# Comprehensive Tool Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance provisioning verification to check all 16+ installed benchmark tools and generate categorized reports of missing tools.

**Architecture:** Add a centralized tool category definition in `defaults/main.yml`, refactor `verify.yml` to check all categories using dynamic loops, collect missing tools by category, output warnings to stdout and create timestamped report files in `benchmarks/verification_reports/`.

**Tech Stack:** Ansible, Jinja2, bash (Linux), PowerShell (Windows)

---

## File Structure

| File | Responsibility | Changes |
|------|---|---|
| `roles/provision_benchmarks/defaults/main.yml` | Central tool category definitions | Add `provision_benchmarks_verification_categories` dict defining all tool groups and their tools |
| `roles/provision_benchmarks/tasks/verify.yml` | Tool verification and reporting | Replace shell task with dynamic category-based checks; add per-category verification; add report generation and stdout warnings |
| `benchmarks/verification_reports/` | NEW | Directory for timestamped verification reports (auto-created by task) |

---

## Task 1: Define Tool Categories in Defaults

**Files:**
- Modify: `roles/provision_benchmarks/defaults/main.yml`

- [ ] **Step 1: View current defaults structure**

Run: `tail -50 /home/pk/Devel/Ansible/local.gentoomanager/roles/provision_benchmarks/defaults/main.yml`

This shows where to append the new category definitions.

- [ ] **Step 2: Add tool category definitions to defaults/main.yml**

Append this to the end of `roles/provision_benchmarks/defaults/main.yml`:

```yaml
# Tool verification categories for comprehensive post-provisioning checks
# These categories define what tools should be verified and how they're reported
provision_benchmarks_verification_categories:
  compression:
    name: "Compression Tools"
    description: "Essential compression utilities for benchmark suite"
    tools:
      - gzip
      - bzip2
      - xz
      - zstd
      - lz4
      - 7zip
    optional: false
  build:
    name: "Build Tools"
    description: "Essential build and compilation tools"
    tools:
      - make
      - cargo
    optional: false
  crypto:
    name: "Cryptography Tools"
    description: "Encryption and signing tools"
    tools:
      - gpg
    optional: false
  utilities:
    name: "Utilities"
    description: "Standard utility tools"
    tools:
      - diffutils
      - sqlite3
    optional: false
  optional:
    name: "Optional Tools"
    description: "Optional tools, only checked if explicitly provisioned"
    tools:
      - botan
      - mold
      - numpy
      - opencv
      - gimp
      - inkscape
    optional: true

# Flattened list of all tools to check (for simple loops)
provision_benchmarks_all_verification_tools: "{{ provision_benchmarks_verification_categories | dict2items | map(attribute='value.tools') | flatten }}"
```

- [ ] **Step 3: Verify the YAML is valid**

Run: `cd /home/pk/Devel/Ansible/local.gentoomanager && python3 -c "import yaml; yaml.safe_load(open('roles/provision_benchmarks/defaults/main.yml'))" && echo "YAML valid"`

Expected: `YAML valid` printed to stdout

- [ ] **Step 4: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
git add roles/provision_benchmarks/defaults/main.yml
git commit -m "feat: add tool verification categories to defaults

Define categories for compression, build, crypto, utilities, and optional
tools. Include metadata for reporting and filtering based on optional status."
```

---

## Task 2: Create Report Generation Helper Task

**Files:**
- Create: `roles/provision_benchmarks/tasks/generate_verification_report.yml`

- [ ] **Step 1: Create the report generation task file**

Create `roles/provision_benchmarks/tasks/generate_verification_report.yml` with this content:

```yaml
---
# Generate categorized verification report for missing benchmark tools.
# This task creates a timestamped report file and displays warnings on stdout.

- name: Create verification reports directory
  ansible.builtin.file:
    path: "{{ playbook_dir }}/benchmarks/verification_reports"
    state: directory
    mode: '0755'
  delegate_to: localhost
  run_once: true

- name: Generate verification report on Linux
  ansible.builtin.shell:
    cmd: |
      set -e
      
      # Prepare timestamp
      TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
      REPORT_FILE="{{ playbook_dir }}/benchmarks/verification_reports/verification_${TIMESTAMP}.txt"
      
      # Start building the report
      {
        echo "Benchmark Provisioning Verification Report"
        echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        echo "Hostname: {{ inventory_hostname }}"
        echo "Ansible Run Date: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        echo ""
        echo "=== MISSING TOOLS SUMMARY ==="
      } > "$REPORT_FILE"
      
      # Count missing tools per category
      declare -A category_missing
      declare -A category_total
      total_missing=0
      
      {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
      category_missing[{{ cat_name | quote }}]={{ _provision_benchmarks_verify_missing[cat_name] | length }}
      category_total[{{ cat_name | quote }}]={{ cat_data.tools | length }}
      {% endfor %}
      
      # Calculate total missing
      for category in "${!category_missing[@]}"; do
        total_missing=$((total_missing + ${category_missing[$category]}))
      done
      
      echo "Total Missing: $total_missing tools" >> "$REPORT_FILE"
      echo "" >> "$REPORT_FILE"
      echo "=== BY CATEGORY ===" >> "$REPORT_FILE"
      echo "" >> "$REPORT_FILE"
      
      # Report each category
      {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
      {
        echo "{{ cat_data.name }} ({{ _provision_benchmarks_verify_missing[cat_name] | length }}/{{ cat_data.tools | length }} missing):"
        {% if _provision_benchmarks_verify_missing[cat_name] | length == 0 %}
          echo "  ✓ All tools present: {{ cat_data.tools | join(', ') }}"
        {% else %}
          {% for tool in cat_data.tools %}
            {% if tool in _provision_benchmarks_verify_missing[cat_name] %}
          echo "  ✗ {{ tool }}"
            {% else %}
          echo "  ✓ {{ tool }}"
            {% endif %}
          {% endfor %}
        {% endif %}
        echo ""
      } >> "$REPORT_FILE"
      {% endfor %}
      
      # Print the report
      cat "$REPORT_FILE"
      
      # Also write to debug log
      echo "Verification report written to: $REPORT_FILE" >&2
  args:
    executable: /bin/bash
  register: _provision_benchmarks_report_result
  changed_when: false
  when: ansible_system != "Windows"

- name: Display report summary (Linux)
  ansible.builtin.debug:
    msg: "{{ _provision_benchmarks_report_result.stdout_lines }}"
  when: ansible_system != "Windows"

- name: Generate verification report on Windows
  ansible.windows.win_shell: |
    $timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $reportFile = "{{ playbook_dir }}\benchmarks\verification_reports\verification_$timestamp.txt"
    
    # Ensure directory exists
    $reportDir = Split-Path -Parent $reportFile
    if (-not (Test-Path $reportDir)) {
      New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    }
    
    $report = @()
    $report += "Benchmark Provisioning Verification Report"
    $report += "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC')"
    $report += "Hostname: {{ inventory_hostname }}"
    $report += "Ansible Run Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC')"
    $report += ""
    $report += "=== MISSING TOOLS SUMMARY ==="
    
    # Count and report missing tools per category
    $totalMissing = 0
    {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
    $missingCount_{{ cat_name }} = {{ _provision_benchmarks_verify_missing[cat_name] | length }}
    $totalCount_{{ cat_name }} = {{ cat_data.tools | length }}
    $totalMissing += $missingCount_{{ cat_name }}
    {% endfor %}
    
    $report += "Total Missing: $totalMissing tools"
    $report += ""
    $report += "=== BY CATEGORY ==="
    $report += ""
    
    {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
    $report += "{{ cat_data.name }} ($($missingCount_{{ cat_name }})/$($totalCount_{{ cat_name }}) missing):"
    {% if _provision_benchmarks_verify_missing[cat_name] | length == 0 %}
    $report += "  ✓ All tools present: {{ cat_data.tools | join(', ') }}"
    {% else %}
    {% for tool in cat_data.tools %}
    {% if tool in _provision_benchmarks_verify_missing[cat_name] %}
    $report += "  ✗ {{ tool }}"
    {% else %}
    $report += "  ✓ {{ tool }}"
    {% endif %}
    {% endfor %}
    {% endif %}
    $report += ""
    {% endfor %}
    
    # Write report
    $report | Out-File -FilePath $reportFile -Encoding utf8
    Write-Host "Verification report written to: $reportFile"
    Write-Host ""
    $report | ForEach-Object { Write-Host $_ }
  register: _provision_benchmarks_report_result_win
  changed_when: false
  when: ansible_system == "Windows"

- name: Display report summary (Windows)
  ansible.builtin.debug:
    msg: "{{ _provision_benchmarks_report_result_win.stdout }}"
  when: ansible_system == "Windows"
```

- [ ] **Step 2: Verify YAML syntax**

Run: `ansible-lint /home/pk/Devel/Ansible/local.gentoomanager/roles/provision_benchmarks/tasks/generate_verification_report.yml`

Expected: No errors, or only warnings about task names (which will be fixed in next task)

- [ ] **Step 3: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
git add roles/provision_benchmarks/tasks/generate_verification_report.yml
git commit -m "feat: add verification report generation task

Generate categorized verification reports showing missing tools per category.
Reports are timestamped and saved to benchmarks/verification_reports/.
Output includes both stdout display and persistent file logging."
```

---

## Task 3: Refactor Verification Task to Check All Tool Categories

**Files:**
- Modify: `roles/provision_benchmarks/tasks/verify.yml`

- [ ] **Step 1: Backup current verify.yml**

```bash
cp /home/pk/Devel/Ansible/local.gentoomanager/roles/provision_benchmarks/tasks/verify.yml /tmp/verify.yml.backup
cat /tmp/verify.yml.backup
```

This saves the current content for reference.

- [ ] **Step 2: Replace verify.yml with comprehensive category-based verification**

Replace entire content of `roles/provision_benchmarks/tasks/verify.yml` with:

```yaml
---
# Comprehensive verification that all benchmark tools are available.
# Checks all categories: compression, build, crypto, utilities, and optional tools.
# Includes both Linux and Windows support.
# Generates categorized reports and displays warnings for missing tools.

- name: Verify essential tools are available (Linux)
  ansible.builtin.shell:
    cmd: |
      set -e
      # Check all tools and build a dict of missing tools by category
      
      # Initialize associative arrays for each category
      {% for cat_name in provision_benchmarks_verification_categories.keys() %}
      declare -a missing_{{ cat_name }}
      {% endfor %}
      
      # Check each category's tools
      {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
      # Check {{ cat_data.name }}
      {% for tool in cat_data.tools %}
      if ! command -v {{ tool }} >/dev/null 2>&1; then
        missing_{{ cat_name }}+=({{ tool | quote }})
      fi
      {% endfor %}
      {% endfor %}
      
      # Output missing tools in machine-parseable format
      # Format: CATEGORY:tool1,tool2,tool3
      {% for cat_name in provision_benchmarks_verification_categories.keys() %}
      missing_list="{{ "${missing_" }}{{ cat_name }}[@]{{ "}" }}"
      echo "MISSING_{{ cat_name | upper }}:$(IFS=,; echo "${missing_list[*]}")"
      {% endfor %}
  args:
    executable: /bin/bash
  register: _provision_benchmarks_verify_raw
  changed_when: false
  failed_when: false
  when: ansible_system != "Windows"

- name: Parse verification results (Linux)
  ansible.builtin.set_fact:
    _provision_benchmarks_verify_missing: "{{ _provision_benchmarks_verify_missing | default({}) | combine({item.split(':')[0] | replace('MISSING_', '') | lower: (item.split(':')[1].split(',') if item.split(':')[1] else [])}) }}"
  loop: "{{ _provision_benchmarks_verify_raw.stdout_lines }}"
  when:
    - ansible_system != "Windows"
    - item.startswith('MISSING_')
  changed_when: false

- name: Ensure all categories in missing dict (Linux)
  ansible.builtin.set_fact:
    _provision_benchmarks_verify_missing: "{{ _provision_benchmarks_verify_missing | default({}) | combine({item: (_provision_benchmarks_verify_missing.get(item, []))}) }}"
  loop: "{{ provision_benchmarks_verification_categories.keys() | list }}"
  when: ansible_system != "Windows"
  changed_when: false

- name: Verify essential tools are available (Windows)
  ansible.windows.win_shell: |
    # Check all tools by category on Windows
    {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
    $missing_{{ cat_name }} = @()
    {% for tool in cat_data.tools %}
    if (-not (Get-Command '{{ tool }}' -ErrorAction SilentlyContinue)) {
      $missing_{{ cat_name }} += '{{ tool }}'
    }
    {% endfor %}
    Write-Output "MISSING_{{ cat_name | upper }}:$($missing_{{ cat_name }} -join ',')"
    {% endfor %}
  register: _provision_benchmarks_verify_raw_win
  changed_when: false
  when: ansible_system == "Windows"

- name: Parse verification results (Windows)
  ansible.builtin.set_fact:
    _provision_benchmarks_verify_missing: "{{ _provision_benchmarks_verify_missing | default({}) | combine({item.split(':')[0] | replace('MISSING_', '') | lower: (item.split(':')[1].split(',') | reject('==', '') | list if item.split(':')[1] else [])}) }}"
  loop: "{{ _provision_benchmarks_verify_raw_win.stdout_lines }}"
  when:
    - ansible_system == "Windows"
    - item.startswith('MISSING_')
  changed_when: false

- name: Ensure all categories in missing dict (Windows)
  ansible.builtin.set_fact:
    _provision_benchmarks_verify_missing: "{{ _provision_benchmarks_verify_missing | default({}) | combine({item: (_provision_benchmarks_verify_missing.get(item, []))}) }}"
  loop: "{{ provision_benchmarks_verification_categories.keys() | list }}"
  when: ansible_system == "Windows"
  changed_when: false

- name: Display tool availability summary
  ansible.builtin.debug:
    msg: |
      === Tool Availability Summary ===
      {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
      
      {{ cat_data.name }} ({{ _provision_benchmarks_verify_missing[cat_name] | length }}/{{ cat_data.tools | length }} missing):
      {% for tool in cat_data.tools %}
      {% if tool in _provision_benchmarks_verify_missing[cat_name] %}
        ✗ {{ tool }}
      {% else %}
        ✓ {{ tool }}
      {% endif %}
      {% endfor %}
      {% endfor %}
  changed_when: false

- name: Warn about missing non-optional tools
  ansible.builtin.debug:
    msg: |
      [WARNING] {{ inventory_hostname }}: Missing non-optional tools:
      {% for cat_name, cat_data in provision_benchmarks_verification_categories.items() %}
      {% if not cat_data.optional and _provision_benchmarks_verify_missing[cat_name] | length > 0 %}
      - {{ cat_data.name }}: {{ _provision_benchmarks_verify_missing[cat_name] | join(', ') }}
      {% endif %}
      {% endfor %}
  when: _provision_benchmarks_verify_missing | dict2items | map(attribute='value') | flatten | length > 0
  changed_when: false

- name: Include report generation
  ansible.builtin.include_tasks: generate_verification_report.yml
```

- [ ] **Step 3: Validate the new verify.yml syntax**

Run: `ansible-lint /home/pk/Devel/Ansible/local.gentoomanager/roles/provision_benchmarks/tasks/verify.yml`

Expected: No errors, or only warnings that don't block execution

- [ ] **Step 4: Commit**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
git add roles/provision_benchmarks/tasks/verify.yml
git commit -m "refactor: enhance verification to check all tool categories

Replace simple bash verification with dynamic category-based checking:
- Support all 16+ missing tool categories (compression, build, crypto, utilities, optional)
- Work on both Linux and Windows
- Parse results into structured dict for reporting
- Warn about missing non-optional tools
- Include report generation task"
```

---

## Task 4: Integration Test — Run Provisioning and Verify Reports

**Files:**
- Test: Full provisioning run on a test VM

- [ ] **Step 1: Verify playbook syntax**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
ansible-playbook playbooks/provision_benchmarks.yml --syntax-check
```

Expected: `playbook: playbooks/provision_benchmarks.yml` (no errors)

- [ ] **Step 2: Run all existing tests to ensure no regression**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
make test lint
```

Expected: All tests pass, no new linting issues

- [ ] **Step 3: Simulate verification on a single host (dry-run)**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
ansible-playbook playbooks/provision_benchmarks.yml \
  --check \
  --limit "gentoo-caramel" \
  -v
```

Expected: Playbook completes in check mode without errors

- [ ] **Step 4: Create test directory structure**

```bash
mkdir -p /home/pk/Devel/Ansible/local.gentoomanager/benchmarks/verification_reports
```

- [ ] **Step 5: Commit the test directory**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
git add -f benchmarks/verification_reports/.gitkeep || true
git commit -m "chore: add verification_reports directory

Directory will hold timestamped verification reports from provisioning runs."
```

- [ ] **Step 6: Verify directory structure**

```bash
find /home/pk/Devel/Ansible/local.gentoomanager/benchmarks -type d -name verification_reports
```

Expected: Shows path to verification_reports directory

---

## Task 5: Documentation Update

**Files:**
- Modify: `roles/provision_benchmarks/README.md` (if exists)

- [ ] **Step 1: Check if README exists**

```bash
ls -la /home/pk/Devel/Ansible/local.gentoomanager/roles/provision_benchmarks/README.md
```

- [ ] **Step 2: If README exists, append documentation**

If the file exists, append this section:

```markdown
## Tool Verification

After provisioning completes, the `verify.yml` task checks that all required and optional benchmark tools are installed:

### Verification Categories

- **Compression Tools:** gzip, bzip2, xz, zstd, lz4, 7zip
- **Build Tools:** make, cargo
- **Crypto Tools:** gpg
- **Utilities:** diffutils, sqlite3
- **Optional Tools:** botan, mold, numpy, opencv, gimp, inkscape

### Output

Verification results are displayed in two ways:

1. **Console Output:** Summary of all tools showing which are present/missing, with warnings for missing non-optional tools
2. **Timestamped Reports:** Detailed reports saved to `benchmarks/verification_reports/verification_YYYY-MM-DD_HHMMSS.txt`

Each report includes a categorical breakdown of missing tools and can be reviewed later to identify provisioning gaps across multiple hosts.
```

- [ ] **Step 3: Commit documentation update**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
git add roles/provision_benchmarks/README.md 2>/dev/null || echo "No README to update"
git commit -m "docs: document verification categories and reporting" 2>/dev/null || echo "No changes to commit"
```

---

## Task 6: Final Validation and Cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run ShellCheck on generated task**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
python3 scripts/shellcheck_yaml_blocks.py roles/provision_benchmarks/tasks/*.yml
shellcheck scripts/*.sh 2>/dev/null || true
```

Expected: No shell syntax errors

- [ ] **Step 2: Run ansible-lint on all task files**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
ansible-lint roles/provision_benchmarks/tasks/verify.yml roles/provision_benchmarks/tasks/generate_verification_report.yml
```

Expected: No errors (warnings acceptable)

- [ ] **Step 3: Verify git history**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
git log --oneline -6
```

Expected: See 4 commits from this implementation plan

- [ ] **Step 4: Final test — run full test suite**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
make test lint shellcheck
```

Expected: All checks pass

- [ ] **Step 5: Display final summary**

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager
git diff HEAD~5 HEAD --name-only
```

Expected: Shows changes to defaults/main.yml, verify.yml, new generate_verification_report.yml, and new .gitkeep

---

## Validation Checklist

After all tasks complete:

- ✅ `provision_benchmarks_verification_categories` dict exists in defaults/main.yml with all 5 categories
- ✅ `generate_verification_report.yml` created with report generation logic
- ✅ `verify.yml` refactored to check all tool categories (compression, build, crypto, utilities, optional)
- ✅ Verification works on both Linux and Windows
- ✅ Missing tools parsed into `_provision_benchmarks_verify_missing` dict
- ✅ Warnings displayed for missing non-optional tools
- ✅ Timestamped reports created in `benchmarks/verification_reports/`
- ✅ `benchmarks/verification_reports/` directory exists
- ✅ All existing tests pass (no regression)
- ✅ ansible-lint passes on new/modified tasks
- ✅ ShellCheck passes on embedded shell blocks
- ✅ 4-5 logical commits with clear messages

---

## Self-Review Against Spec

**Spec Coverage:**
- ✅ Verify all installed tools (16+) — Task 1 defines categories, Task 3 checks them
- ✅ Categorized output — Task 3 organizes by category
- ✅ Dual reporting (stdout + file) — Task 2 handles both
- ✅ Report persistence in `benchmarks/verification_reports/` — Task 2 implements
- ✅ OS compatibility (Linux/Windows) — Tasks 2 & 3 branch on ansible_system
- ✅ Optional tool handling — Task 1 marks optional; Task 3 warns conditionally
- ✅ Non-blocking — All tasks use changed_when: false, no failed_when
- ✅ Report format — Categorized, human-readable, timestamped
- ✅ Tests — Task 4 validates playbook syntax and dry-run
- ✅ Documentation — Task 5 updates README

**Placeholder Scan:** None found. All code blocks are complete with exact commands and outputs specified.

**Type Consistency:** All vars use consistent naming (`_provision_benchmarks_verify_*`), dict keys match across tasks.

**Scope:** Plan is focused on verification enhancement only, no unrelated changes.

