/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import express from "express";
import session from "express-session";
import jwt from "jsonwebtoken";
import path from "node:path";
import { fileURLToPath } from "node:url";

declare module "express-session" {
  interface SessionData {
    viewer?: "usa" | "france";
  }
}

const secret = process.env.FOCAL_EMBED_SECRET;
const sessionSecret = process.env.FOCAL_SESSION_SECRET;
const dashboardUuid = process.env.FOCAL_DASHBOARD_UUID;
const dashboardId = Number(process.env.FOCAL_DASHBOARD_ID);
const datasetId = Number(process.env.FOCAL_DATASET_ID);
const port = Number(process.env.PORT || 3100);
const origin = `http://localhost:${port}`;
const supersetDomain = "http://localhost:8088";
if (process.env.NODE_ENV === "production") {
  throw new Error(
    "This local demo requires real website authentication before production use.",
  );
}
if (
  !secret ||
  secret.length < 32 ||
  !sessionSecret ||
  sessionSecret.length < 32 ||
  !dashboardUuid ||
  !Number.isSafeInteger(dashboardId) ||
  !Number.isSafeInteger(datasetId)
) {
  throw new Error("Missing embedding configuration. Run setup.ps1 first.");
}
const viewers = {
  usa: { label: "US sales team", country: "USA" },
  france: { label: "France sales team", country: "France" },
} as const;
const app = express();
app.disable("x-powered-by");
app.use((req, res, next) => {
  if (
    req.headers.host !== `localhost:${port}` &&
    req.headers.host !== `127.0.0.1:${port}`
  ) {
    res.sendStatus(403);
    return;
  }
  res.set({
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": `default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src ${supersetDomain}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`,
  });
  if (req.path.startsWith("/api/")) res.set("Cache-Control", "no-store");
  if (
    req.method !== "GET" &&
    req.method !== "HEAD" &&
    (req.headers.origin !== origin || !req.is("application/json"))
  ) {
    res.sendStatus(403);
    return;
  }
  next();
});
app.use(express.json({ limit: "2kb" }));
app.use(
  session({
    name: "focal_demo_session",
    secret: sessionSecret,
    resave: false,
    saveUninitialized: false,
    cookie: {
      httpOnly: true,
      sameSite: "strict",
      secure: false,
      maxAge: 60 * 60 * 1000,
    },
  }),
);
app.get("/api/session", (req, res) => {
  const key = req.session.viewer;
  res.json({ viewer: key ? { id: key, ...viewers[key] } : null });
});
// Deliberate local demo identity selector, not a production login endpoint.
app.post("/api/demo/session", (req, res, next) => {
  const viewer: unknown = req.body?.viewer;
  if (
    (viewer !== "usa" && viewer !== "france") ||
    Object.keys(req.body).length !== 1
  ) {
    res.status(400).json({ error: "Choose a supported demo viewer." });
    return;
  }
  req.session.regenerate((error) => {
    if (error) {
      next(error);
      return;
    }
    req.session.viewer = viewer;
    req.session.save((saveError) => {
      if (saveError) {
        next(saveError);
        return;
      }
      res.json({ viewer: { id: viewer, ...viewers[viewer] } });
    });
  });
});
app.post("/api/logout", (req, res, next) => {
  req.session.destroy((error) => {
    if (error) {
      next(error);
      return;
    }
    res.clearCookie("focal_demo_session");
    res.sendStatus(204);
  });
});
app.get("/api/analytics/config", (req, res) => {
  if (!req.session.viewer) {
    res.sendStatus(401);
    return;
  }
  res.json({ dashboardUuid, dashboardId, datasetId, supersetDomain });
});
app.get("/api/analytics/guest-token", (req, res) => {
  const key = req.session.viewer;
  if (!key) {
    res.sendStatus(401);
    return;
  }
  // No client-supplied dashboard IDs, row rules, countries or posts are accepted.
  if (Object.keys(req.query).length) {
    res.sendStatus(400);
    return;
  }
  const viewer = viewers[key];
  const token = jwt.sign(
    {
      type: "guest",
      user: {
        username: `demo-${key}`,
        first_name: viewer.label,
        last_name: "",
      },
      resources: [{ type: "dashboard", id: dashboardUuid }],
      // Server-owned constant values; never interpolate browser input into SQL.
      rls_rules: [
        { dataset: datasetId, clause: `country = '${viewer.country}'` },
      ],
    },
    secret,
    { algorithm: "HS256", audience: "focalbi-embedded", expiresIn: "5m" },
  );
  res.json({ token, issuedAt: new Date().toISOString() });
});
app.use(
  express.static(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "public"),
  ),
);
app.use(
  (
    error: Error,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction,
  ) => {
    console.error(error.message);
    res
      .status(500)
      .json({ error: "The demo could not complete this request." });
  },
);
app.listen(port, "127.0.0.1", () =>
  console.log(`FocalBI demo ready at ${origin}`),
);
