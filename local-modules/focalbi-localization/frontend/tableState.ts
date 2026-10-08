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
export interface ClientTableState {
  pageIndex: number;
  sortBy: unknown;
  globalFilter?: unknown;
}
/** Distinguish presentation redraws from new results and native user actions. */
export class TableDisplayState {
  private snapshot?: { display: unknown; query: unknown; columns: string };
  private retain = false;
  update(display: unknown, query: unknown, columns: string): void {
    if (this.snapshot) {
      if (query !== this.snapshot.query || columns !== this.snapshot.columns)
        this.retain = false;
      else if (display !== this.snapshot.display) this.retain = true;
    }
    this.snapshot = { display, query, columns };
  }
  reduce<S extends ClientTableState>(
    next: S,
    previous: S,
    action: { type: string; pageSize?: number },
    pageSize?: number,
  ): S {
    if (
      this.retain &&
      ["resetPage", "resetSortBy", "resetGlobalFilter"].includes(action.type)
    ) {
      return {
        ...next,
        pageIndex: previous.pageIndex,
        sortBy: previous.sortBy,
        globalFilter: previous.globalFilter,
      };
    }
    if (
      action.type !== "init" &&
      !action.type.startsWith("reset") &&
      action.type !== "setStickyState" &&
      !(action.type === "setPageSize" && action.pageSize === pageSize)
    )
      this.retain = false;
    return next;
  }
}
