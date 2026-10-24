/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
 */
type ObjectValue = Record<string, unknown>;
const isObject = (value: unknown): value is ObjectValue =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Accept explicit group colours only; missing/invalid settings leave native options intact. */
function groupColors(value: unknown): Record<string, string> | undefined {
  if (!isObject(value) || !Object.keys(value).length) return undefined;
  if (
    !Object.values(value).every(
      (color) => typeof color === "string" && /^#[\da-f]{6}$/i.test(color),
    )
  )
    return undefined;
  return value as Record<string, string>;
}

/** Mix with white using a stable path hash, independent of value, sort and filters. */
function shade(base: string, path: string[]): string {
  let hash = 2166136261;
  for (const char of JSON.stringify(path))
    hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  const amount = 0.2 + ((hash >>> 0) % 9) * 0.065;
  return (
    "#" +
    [1, 3, 5]
      .map((offset) => {
        const channel = parseInt(base.slice(offset, offset + 2), 16);
        return Math.round(channel + (255 - channel) * amount)
          .toString(16)
          .padStart(2, "0");
      })
      .join("")
  );
}

function labelColor(color: string): string {
  const linear = [1, 3, 5].map((offset) => {
    const channel = parseInt(color.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  const luminance =
    linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  return luminance > 0.179 ? "#000000" : "#ffffff";
}

function paint(
  node: ObjectValue,
  base: string,
  path: string[],
  parent: boolean,
): ObjectValue {
  const color = parent ? base : shade(base, path);
  return {
    ...node,
    colorSaturation: undefined,
    itemStyle: { ...(isObject(node.itemStyle) ? node.itemStyle : {}), color },
    label: {
      ...(isObject(node.label) ? node.label : {}),
      color: labelColor(color),
    },
    ...(Array.isArray(node.children)
      ? {
          children: node.children.map((child) =>
            isObject(child)
              ? paint(child, base, [...path, String(child.name)], false)
              : child,
          ),
        }
      : {}),
  };
}

/** Recolour native treemap branches below its metric root, preserving values and identities. */
export function colorTreemapGroups(
  props: ObjectValue,
  setting: unknown,
): ObjectValue {
  const colors = groupColors(setting);
  const options = props.echartOptions;
  if (!colors || !isObject(options) || !Array.isArray(options.series))
    return props;
  return {
    ...props,
    echartOptions: {
      ...options,
      series: options.series.map((series) => {
        if (
          !isObject(series) ||
          series.type !== "treemap" ||
          !Array.isArray(series.data)
        )
          return series;
        return {
          ...series,
          data: series.data.map((root) =>
            !isObject(root) || !Array.isArray(root.children)
              ? root
              : {
                  ...root,
                  children: root.children.map((group) => {
                    if (
                      !isObject(group) ||
                      !Object.hasOwn(colors, String(group.name))
                    )
                      return group;
                    return paint(
                      group,
                      colors[String(group.name)],
                      [String(group.name)],
                      true,
                    );
                  }),
                },
          ),
        };
      }),
    },
  };
}
