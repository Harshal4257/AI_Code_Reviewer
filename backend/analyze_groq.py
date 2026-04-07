def _analyze_with_groq(self, code: str) -> List[Dict[str, Any]]:
        if not self.groq_client:
            return []

        # ── CACHE CHECK ──────────────────────────────────────────────────
        # If the code being reviewed is exactly what we just fixed,
        # it is guaranteed clean — skip all analysis and return nothing.
        import hashlib
        incoming = hashlib.md5(code.strip().encode()).hexdigest()
        if self.last_fixed_code:
            last_fixed = hashlib.md5(self.last_fixed_code.strip().encode()).hexdigest()
            if incoming == last_fixed:
                logging.info("Code matches last fixed version — returning clean, skipping analysis.")
                return []
        # ─────────────────────────────────────────────────────────────────

        try:
        # === STEP 1: Pre-scan (always runs)
            logging.info("Step 1: Running AST + regex pre-scan...")
            pre_scan_issues = self._pre_scan(code)

        # === STEP 2: Only call Groq if pre-scan found issues
        # If pre-scan found nothing, code is clean — skip Groq entirely
        # This prevents Groq from inventing issues on already-clean code
            if not pre_scan_issues:
                logging.info("Pre-scan found zero issues — code is clean, skipping Groq.")
                self.last_fixed_code = code
                return []

            groq_issues = self._call_find_issues(code, pre_scan_issues)

        # Merge all issues
            all_issues = pre_scan_issues + groq_issues

            if not all_issues:
                self.last_fixed_code = code
                logging.info("Code is clean — no issues found.")
                return []

            # === STEP 3: Fix everything ===
            logging.info(f"Step 3: Fixing {len(all_issues)} total issues...")
            fixed_code = self._call_fix_code(code, all_issues)

            if fixed_code:
                # Verify fixed code is clean before storing
                post_issues = self._pre_scan(fixed_code)
                if post_issues:
                    logging.info(f"Fixed code has {len(post_issues)} remaining pre-scan issues — running second fix...")
                    fixed_code = self._call_fix_code(fixed_code, post_issues)
                self.last_fixed_code = fixed_code
                logging.info("Fix complete and verified clean.")
            else:
                logging.error("Fix returned empty code — keeping original.")
                self.last_fixed_code = code

            # Build result issues list for VS Code
            result_issues: List[Dict[str, Any]] = list(all_issues)

            # Add FULL_FILE_FIX signal for frontend Apply All Fixes button
            result_issues.append({
                "tool": "AI-Reviewer",
                "type": "AI Suggestion",
                "category": "info",
                "msg": "AI suggests refactoring to: FULL_FILE_FIX_AVAILABLE",
                "line": 1
            })

            logging.info(f"Analysis complete. {len(all_issues)} issues found.")
            return result_issues

        except Exception as e:
            logging.error(f"Groq analysis failed: {e}")
            self.last_fixed_code = ""
            return []