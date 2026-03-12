# Local Gentoomanager Collection Release Notes

**Topics**

- <a href="#v1-0-0">v1\.0\.0</a>
    - <a href="#release-summary">Release Summary</a>
    - <a href="#major-changes">Major Changes</a>
    - <a href="#minor-changes">Minor Changes</a>
    - <a href="#removed-features-previously-deprecated">Removed Features \(previously deprecated\)</a>
    - <a href="#security-fixes">Security Fixes</a>
    - <a href="#bugfixes">Bugfixes</a>

<a id="v1-0-0"></a>
## v1\.0\.0

<a id="release-summary"></a>
### Release Summary

Initial release of the Local Gentoomanager Collection\, providing Gentoo
configuration management\, a comprehensive hyperfine\-based benchmark suite\,
USE flag collection\, and full CI/CD pipeline support\.

<a id="major-changes"></a>
### Major Changes

* Added <code>probe\_command\_output</code> Ansible module to run structured shell probes and return their output as a dict\, replacing fragile inline Python tasks\.
* Added a GitHub Actions CI pipeline covering shellcheck\, ansible\-lint\, ansible\-test sanity\, pytest unit tests\, and molecule integration tests\.
* Added a USE flag and <code>make\.conf</code> collection system that writes per\-host results into <code>host\_vars</code> and shared settings into <code>group\_vars/all</code>\.
* Added a benchmark report generator \(<code>scripts/generate\_benchmark\_report\.py</code>\) producing a Markdown table report and an interactive HTML5 report with Chart\.js charts from collected JSON results\.
* Added a hyperfine\-based benchmark suite covering ten categories — compression \(gzip\, bzip2\, xz\, zstd\, lz4\)\, crypto \(OpenSSL\, GPG\)\, compiler efficiency \(gcc\, clang\, rustc\, go\)\, Python performance\, FFmpeg encode/decode\, coreutils and dev tools\, OpenCV \(Kodak corpus\)\, ImageMagick\, GIMP\, and Inkscape\.

<a id="minor-changes"></a>
### Minor Changes

* Added 14 additional host environment characteristics to benchmark result JSON \(scheduler\, filesystem\, swap\, CPU flags\, compiler versions\, CFLAGS\, etc\.\)\.
* Added CPU performance normalisation using 7\-zip calibration scores and PassMark lookups so results are comparable across heterogeneous hosts\.
* Added Rust provisioning strategy for Gentoo — <code>dev\-lang/rust</code> \(source build\) is attempted first\; <code>dev\-lang/rust\-bin</code> is used as a fallback\. <code>eselect rust update</code> activates the latest slot after either install\.
* Added SSH setup guide \(<code>docs/setup\-access\.md</code>\) covering passwordless SSH\, ssh\-agent management under systemd\, OpenRC\, runit\, s6\, launchd\, and FreeBSD\, storing passphrases in ansible\-vault\, and choosing the remote user\.
* Added VM RAM scaling around Gentoo provisioning — memory is raised to the maximum before building packages from source and restored afterwards using <code>virsh setmem \-\-live</code> delegated to the hypervisor\.
* Added <code>sqlite3</code> and <code>numpy</code> to the provisioned package list for all supported operating systems\.
* Added comprehensive pytest unit tests covering the report generator\, USE flag collapse script\, benchmark image generator\, fixture downloader\, inventory generator\, and shellcheck wrapper\.
* Added development guide \(<code>docs/development\.md</code>\) covering uv/pip tooling and running tests locally\.
* Added hypervisor benchmark play to collect bare\-metal reference measurements when benchmark tools are present on the hypervisor host\.
* Added molecule integration test scenario <code>integration\_probe\_command\_output</code> for local verification of the module without a VM\.
* Added per\-version <code>tests/sanity/ignore\-2\.1X\.txt</code> files so standalone scripts and test files are exempt from collection\-module shebang and style rules\.
* Expanded OpenSSL crypto benchmarks to cover AES\-GCM\, ChaCha20\-Poly1305\, SHA\-256/512\, RSA\-2048/4096\, and ECDSA\; <code>\-evp</code> flag used for AEAD ciphers\.
* Reduced benchmark suite run time by approximately 54 percent across slow categories by tuning <code>\-\-runs</code> and <code>\-\-warmup</code> counts and using <code>\-\-shell\=none</code> where possible\.
* Renamed <code>probe\_command\_output</code> module option <code>key</code> to <code>result\_key</code> to avoid the ansible\-lint <code>no\-log\-needed</code> false positive\.
* Switched FreeBSD provisioning from binary <code>pkg</code> packages to building from ports for more accurate performance comparisons\.

<a id="removed-features-previously-deprecated"></a>
### Removed Features \(previously deprecated\)

* Removed <code>ansible\.utils</code> collection dependency — it was unused\.
* Removed <code>host\_vars</code> and <code>group\_vars</code> from version control\; generated files are now gitignored\.
* Removed stale <code>roles/run\_benchmarks/library/probe\_command\_output\.py</code> duplicate\; the canonical module now lives in <code>plugins/modules/</code>\.

<a id="security-fixes"></a>
### Security Fixes

* Resolved 15 findings from an Ansible security audit — added <code>no\_log</code> where needed\, replaced <code>shell</code> with <code>command</code> where possible\, and tightened privilege\-escalation scoping\.

<a id="bugfixes"></a>
### Bugfixes

* Eliminated all Ansible deprecation and lint warnings from the molecule integration test run\.
* Fixed CI workflow <code>tests\.yml</code> which was missing a <code>push\:</code> trigger and referenced branch <code>master</code> instead of <code>main</code>\.
* Fixed OpenSSL speed <code>\-evp</code> flag requirement for AEAD ciphers \(AES\-GCM\, ChaCha20\-Poly1305\)\.
* Fixed <code>\.ansible\-lint</code> invalid <code>include\_paths</code> key that caused ansible\-lint 26\.3 to crash with exit code 3 before linting any files\.
* Fixed <code>doc\-default\-does\-not\-match\-spec</code> in <code>probe\_command\_output</code> — the <code>pattern</code> argument default was inconsistent between <code>argument\_spec</code> and DOCUMENTATION\.
* Fixed <code>probe\_command\_output</code> module — added missing GPLv3 licence header\, <code>author\:</code> field in DOCUMENTATION\, and moved imports after the DOCUMENTATION string to satisfy <code>validate\-modules</code>\.
* Fixed hard\-coded hyperfine version <code>0\.1\.4</code> in provisioning — updated to <code>1\.20\.0</code>\.
* Fixed shellcheck SC2002 \(useless <code>cat</code>\) in <code>normalize\.yml</code>\.
* Fixed shellcheck SC2015 \(<code>A \&\& B \|\| C</code> anti\-pattern\) in <code>ffmpeg\.yml</code> and <code>normalize\.yml</code> by converting to <code>if/then/fi</code> blocks\.
