#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (c) 2024, local.gentoomanager contributors
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function
__metaclass__ = type

"""
Ansible module: probe_command_output

Runs one or more external commands, applies regex patterns to their
combined stdout+stderr (or stdout only), and returns structured data.

Each probe produces either:
  - A sorted, deduplicated list of regex matches  (default)
  - The raw output string, optionally truncated   (raw: true)

This replaces inline ``python3 -c`` blocks inside
``ansible.builtin.shell`` tasks that probe tool capabilities and parse
their output into dicts (e.g. FFmpeg codec discovery, OpenSSL algorithm
discovery).
"""

DOCUMENTATION = r"""
---
module: probe_command_output
short_description: Run commands and extract structured data via regex
description:
  - Runs one or more shell commands on the managed host.
  - For each command, either returns all regex matches as a list, or
    returns the raw output as a string.
  - Results are collected under caller-supplied keys in the C(data)
    return value.
author:
  - Contributors (@feinorgh)
options:
  probes:
    description:
      - List of probe descriptors.
    type: list
    elements: dict
    required: true
    suboptions:
      output_name:
        description: Key name for this probe's result in C(data).
        type: str
        required: true
      command:
        description: Command to run, as a list of strings.
        type: list
        elements: str
        required: true
      pattern:
        description:
          - Regular expression applied to the command output.
          - Required unless C(raw) is C(true).
        type: str
        default: ""
      group:
        description: Capture group index to extract (1-based).
        type: int
        default: 1
      combine_stderr:
        description: Include stderr in the text that the regex is applied to.
        type: bool
        default: false
      raw:
        description:
          - Return the raw output string instead of regex matches.
          - When C(true), C(pattern) is ignored.
        type: bool
        default: false
      max_length:
        description:
          - Truncate raw output to this many characters (0 = unlimited).
        type: int
        default: 0
      sort:
        description: Sort the list of matches.
        type: bool
        default: true
      unique:
        description: Deduplicate the list of matches.
        type: bool
        default: true
  timeout:
    description: Per-command timeout in seconds.
    type: int
    default: 30
"""

EXAMPLES = r"""
- name: Discover available FFmpeg codecs
  local.gentoomanager.probe_command_output:
    probes:
      - output_name: video_encoders
        command: [ffmpeg, -encoders]
        pattern: '^\s*V[\.\w]{5}\s+(\S+)'
      - output_name: audio_encoders
        command: [ffmpeg, -encoders]
        pattern: '^\s*A[\.\w]{5}\s+(\S+)'
      - output_name: video_decoders
        command: [ffmpeg, -decoders]
        pattern: '^\s*V[\.\w]{5}\s+(\S+)'
      - output_name: audio_decoders
        command: [ffmpeg, -decoders]
        pattern: '^\s*A[\.\w]{5}\s+(\S+)'
  register: ffmpeg_codecs

- name: Detect available OpenSSL algorithms
  local.gentoomanager.probe_command_output:
    probes:
      - output_name: ciphers
        command: [openssl, enc, -list]
        pattern: '-(\S+)'
        combine_stderr: true
      - output_name: digests
        command: [openssl, dgst, -list]
        pattern: '-(\S+)'
        combine_stderr: true
      - output_name: speed_help
        command: [openssl, speed, -help]
        combine_stderr: true
        raw: true
        max_length: 2000
  register: openssl_info
"""

RETURN = r"""
data:
  description: >
    Dict mapping each probe's C(output_name) to either a list of regex
    matches or a raw string (when C(raw) is true).
  type: dict
  returned: always
commands_run:
  description: Number of commands actually executed.
  type: int
  returned: always
"""

import re  # noqa: E402
import subprocess  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402


def run_probe(probe: dict, timeout: int) -> tuple[str | list, str | None]:
    """Execute one probe and return (result, error_message)."""
    command = probe["command"]
    combine_stderr = probe.get("combine_stderr", False)
    raw = probe.get("raw", False)
    max_length = probe.get("max_length", 0)
    pattern = probe.get("pattern", "")
    group = probe.get("group", 1)
    do_sort = probe.get("sort", True)
    do_unique = probe.get("unique", True)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return ([] if not raw else ""), f"command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return ([] if not raw else ""), f"command timed out after {timeout}s"
    except OSError as exc:
        return ([] if not raw else ""), str(exc)

    text = result.stdout
    if combine_stderr:
        text = text + result.stderr

    if raw:
        output = text[:max_length] if max_length > 0 else text
        return output, None

    if not pattern:
        return [], "pattern is required when raw is false"

    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        return [], f"invalid regex '{pattern}': {exc}"

    matches = []
    for m in compiled.finditer(text):
        try:
            matches.append(m.group(group))
        except IndexError:
            pass

    if do_unique:
        matches = list(dict.fromkeys(matches))  # preserves order, deduplicates
    if do_sort:
        matches = sorted(matches)

    return matches, None


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            probes=dict(
                type="list",
                elements="dict",
                required=True,
                options=dict(
                output_name=dict(type="str", required=True),
                    command=dict(type="list", elements="str", required=True),
                    pattern=dict(type="str", default=""),
                    group=dict(type="int", default=1),
                    combine_stderr=dict(type="bool", default=False),
                    raw=dict(type="bool", default=False),
                    max_length=dict(type="int", default=0),
                    sort=dict(type="bool", default=True),
                    unique=dict(type="bool", default=True),
                ),
            ),
            timeout=dict(type="int", default=30),
        ),
        supports_check_mode=True,
    )

    probes = module.params["probes"]
    timeout = module.params["timeout"]

    data: dict = {}
    errors: list[str] = []

    for probe in probes:
        result, err = run_probe(probe, timeout)
        data[probe["output_name"]] = result
        if err:
            errors.append(f"{probe['output_name']}: {err}")

    if errors:
        module.exit_json(
            changed=False,
            data=data,
            commands_run=len(probes),
            warnings=errors,
        )
    else:
        module.exit_json(
            changed=False,
            data=data,
            commands_run=len(probes),
        )


if __name__ == "__main__":
    main()
