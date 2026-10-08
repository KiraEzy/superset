/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import type { FocusEvent, KeyboardEvent, ReactNode } from "react";
import { useLayoutEffect, useRef, useState } from "react";
import { Button, Space } from "@superset-ui/core/components";
import { t } from "@apache-superset/core/translation";
import { useControlMessages } from "./ControlMessages";
import {
  filterActionValues,
  type FilterOption,
  type FilterValue,
} from "./filterActions";

interface Props {
  children: ReactNode;
  options: readonly FilterOption[];
  value: readonly unknown[] | null | undefined;
  disabled: boolean;
  onChange: (values: FilterValue[]) => void;
}

/** Keep focus transitions inside the custom popup out of rc-select's blur reset. */
export function filterDropdownBlur(event: FocusEvent<HTMLElement>) {
  const next = event.relatedTarget;
  const current = event.target;
  if (!(current instanceof HTMLElement) || !(next instanceof HTMLElement))
    return;
  const from = current.closest('[data-test="focalbi-filter-dropdown"]');
  const to = next.closest('[data-test="focalbi-filter-dropdown"]');
  if (
    (to && (to === from || filterInput(to) === current)) ||
    (from && filterInput(from) === next)
  ) {
    event.stopPropagation();
  }
}

function filterInput(popup: Element | null) {
  const list = popup?.querySelector('[role="listbox"]');
  const input = popup?.ownerDocument.getElementById(
    list?.id.replace(/_list$/, "") || "",
  );
  return input instanceof HTMLInputElement ? input : null;
}

function focusFilter(popup: Element | null) {
  filterInput(popup)?.focus();
}

/** Superset consumes Tab as selection; reserve it for the popup's real buttons. */
export function filterDropdownKeyDown(event: KeyboardEvent<HTMLElement>) {
  const input = event.target;
  if (
    !(input instanceof HTMLElement) ||
    input.getAttribute("role") !== "combobox" ||
    event.key !== "Tab"
  )
    return;
  const list = input.ownerDocument.getElementById(
    input.getAttribute("aria-controls") || "",
  );
  const popup = list?.closest(".ant-select-dropdown");
  if (input.getAttribute("aria-expanded") !== "true" || !popup) return;
  event.stopPropagation();
  const button = popup.querySelector<HTMLButtonElement>(
    '[data-test="focalbi-filter-dropdown"] button:not(:disabled)',
  );
  if (!event.shiftKey && button) {
    event.preventDefault();
    button.focus();
  }
}

/** Dropdown shortcuts delegate to the native filter's existing change callback. */
export function FilterDropdown({
  children,
  options,
  value,
  disabled,
  onChange,
}: Props) {
  const ui = useControlMessages();
  const popupRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState("");
  // Observe the rendered input locally. Updating parent Select state on input
  // would cancel its pending debounced server search when it re-renders.
  useLayoutEffect(() => {
    const input = filterInput(popupRef.current);
    if (!input) return undefined;
    const sync = () => setSearch(input.value);
    sync();
    input.addEventListener("input", sync);
    return () => input.removeEventListener("input", sync);
  });
  const values = filterActionValues(options, value, search);
  return (
    <div
      ref={popupRef}
      data-test="focalbi-filter-dropdown"
      onKeyDown={(event) => {
        if (event.key !== "Escape") event.stopPropagation();
        else {
          focusFilter(event.currentTarget);
        }
      }}
    >
      <Space
        style={{
          display: "flex",
          justifyContent: "space-between",
          padding: "4px 8px",
        }}
        onMouseDown={(event) => event.preventDefault()}
      >
        <Button
          type="link"
          buttonStyle="link"
          buttonSize="xsmall"
          disabled={disabled || values.additions.length === 0}
          title={ui(
            "filter.selectAvailable",
            t("Select available matching options"),
          )}
          onClick={(event) => {
            if (
              event.currentTarget ===
              event.currentTarget.ownerDocument.activeElement
            )
              focusFilter(
                event.currentTarget.closest(
                  '[data-test="focalbi-filter-dropdown"]',
                ),
              );
            onChange(values.all);
          }}
        >
          {ui("filter.selectAll", t("Select all"))} ({values.additions.length})
        </Button>
        <Button
          type="link"
          buttonStyle="link"
          buttonSize="xsmall"
          disabled={disabled || values.current.length === 0}
          onClick={(event) => {
            if (
              event.currentTarget ===
              event.currentTarget.ownerDocument.activeElement
            )
              focusFilter(
                event.currentTarget.closest(
                  '[data-test="focalbi-filter-dropdown"]',
                ),
              );
            onChange([]);
          }}
        >
          {ui("filter.clearSelection", t("Clear"))} ({values.current.length})
        </Button>
      </Space>
      {children}
    </div>
  );
}
