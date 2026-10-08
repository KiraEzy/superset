/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import type { Locale } from "./contracts";

const english = {
  "filter.heading": "Filters and controls",
  "filter.apply": "Apply filters",
  "filter.applyShort": "Apply",
  "filter.clear": "Clear all",
  "filter.selectAll": "Select all",
  "filter.clearSelection": "Clear",
  "filter.selectAvailable": "Select available matching options",
  "filter.option": "{count} option",
  "filter.options": "{count} options",
  "filter.noData": "No data",
  "filter.excluded": " (excluded)",
  "filter.is": "is",
  "filter.isNot": "is not",
  "filter.otherTabs":
    "Some required filters on other tabs have values and will not be cleared",
  "table.search": "Search",
  "table.searchBy": "Search by",
  "table.searchRecords": "Search {count} records",
  "table.record": "{count} record…",
  "table.records": "{count} records…",
  "table.show": "Show",
  "table.perPage": "entries per page",
  "table.pageSize": "Select page size",
  "table.showPerPage": "Show entries per page",
  "table.showEntries": "Show {count} entries",
  "table.all": "All",
  "table.noRecords": "No records found",
  "table.noMatching": "No matching records found",
  "legend.all": "All",
  "legend.inverse": "Inv",
  "chart.desc": "Value: highest first",
  "chart.asc": "Value: lowest first",
  "chart.total": "Total: {value}",
  "renderer.label": "Renderer",
  "renderer.baseline": "Superset baseline",
  "renderer.fork": "FocalBI fork",
} as const;
export type ControlKey = keyof typeof english;
export type ControlParameters = Readonly<Record<string, string | number>>;
const messages: Record<Locale, Record<ControlKey, string>> = {
  en: english,
  "zh-Hant": {
    "filter.heading": "篩選與控制",
    "filter.apply": "套用篩選",
    "filter.applyShort": "套用",
    "filter.clear": "清除全部",
    "filter.selectAll": "全選",
    "filter.clearSelection": "清除",
    "filter.selectAvailable": "選取目前可用的相符選項",
    "filter.option": "{count} 個選項",
    "filter.options": "{count} 個選項",
    "filter.noData": "沒有資料",
    "filter.excluded": "（已排除）",
    "filter.is": "是",
    "filter.isNot": "不是",
    "filter.otherTabs": "其他分頁的部分必填篩選已有選取值，不會被清除",
    "table.search": "搜尋",
    "table.searchBy": "搜尋欄位",
    "table.searchRecords": "搜尋 {count} 筆資料",
    "table.record": "{count} 筆資料…",
    "table.records": "{count} 筆資料…",
    "table.show": "每頁顯示",
    "table.perPage": "筆資料",
    "table.pageSize": "選擇每頁資料筆數",
    "table.showPerPage": "每頁顯示筆數",
    "table.showEntries": "顯示 {count} 筆資料",
    "table.all": "全部",
    "table.noRecords": "沒有資料",
    "table.noMatching": "找不到符合條件的資料",
    "legend.all": "全選",
    "legend.inverse": "反選",
    "chart.desc": "數值：由高至低",
    "chart.asc": "數值：由低至高",
    "chart.total": "總計：{value}",
    "renderer.label": "圖表呈現引擎",
    "renderer.baseline": "Superset 基準版",
    "renderer.fork": "FocalBI 分支版",
  },
  "zh-Hans": {
    "filter.heading": "筛选与控制",
    "filter.apply": "应用筛选",
    "filter.applyShort": "应用",
    "filter.clear": "清除全部",
    "filter.selectAll": "全选",
    "filter.clearSelection": "清除",
    "filter.selectAvailable": "选择当前可用的匹配选项",
    "filter.option": "{count} 个选项",
    "filter.options": "{count} 个选项",
    "filter.noData": "没有数据",
    "filter.excluded": "（已排除）",
    "filter.is": "是",
    "filter.isNot": "不是",
    "filter.otherTabs": "其他分页的部分必填筛选已有选取值，不会被清除",
    "table.search": "搜索",
    "table.searchBy": "搜索字段",
    "table.searchRecords": "搜索 {count} 条记录",
    "table.record": "{count} 条记录…",
    "table.records": "{count} 条记录…",
    "table.show": "每页显示",
    "table.perPage": "条记录",
    "table.pageSize": "选择每页记录条数",
    "table.showPerPage": "每页显示条数",
    "table.showEntries": "显示 {count} 条记录",
    "table.all": "全部",
    "table.noRecords": "没有记录",
    "table.noMatching": "找不到符合条件的记录",
    "legend.all": "全选",
    "legend.inverse": "反选",
    "chart.desc": "数值：从高到低",
    "chart.asc": "数值：从低到高",
    "chart.total": "总计：{value}",
    "renderer.label": "图表渲染引擎",
    "renderer.baseline": "Superset 基准版",
    "renderer.fork": "FocalBI 分支版",
  },
};
/** Viewer-owned control text; never installs a global application catalog. */
export function controlMessage(
  locale: Locale,
  key: ControlKey,
  parameters: ControlParameters = {},
): string {
  return messages[locale][key].replace(/\{(\w+)\}/g, (token, name: string) =>
    Object.hasOwn(parameters, name) ? String(parameters[name]) : token,
  );
}
/** Preserve the native formatter's output, including currency and compact units. */
export function localizeTotal(
  locale: Locale,
  original: string,
  nativeTemplate = "Total: {value}",
): string {
  const parts = nativeTemplate.split("{value}");
  if (
    parts.length !== 2 ||
    !original.startsWith(parts[0]) ||
    !original.endsWith(parts[1])
  )
    return original;
  return controlMessage(locale, "chart.total", {
    value: original.slice(
      parts[0].length,
      parts[1] ? -parts[1].length : undefined,
    ),
  });
}
