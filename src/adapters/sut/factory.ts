import type { SUTAdapter } from "../../domains/research/contracts/adapters.js";
import type { RunManifest } from "../../schemas/contracts.js";
import { FakeResearchAdapter } from "./fake/adapter.js";
import { ProcessResearchAdapter, processOptionsFromManifest } from "./process/adapter.js";
import { HttpResearchAdapter, httpOptionsFromManifest } from "./api/http-adapter.js";
import { DoubaoBatchAdapter, doubaoOptionsFromManifest } from "./web/doubao/facade.js";

export function createSUTAdapter(manifest: RunManifest): SUTAdapter {
  if (manifest.sut.adapter === "fake") return new FakeResearchAdapter();
  if (manifest.sut.adapter === "doubao_web") {
    return new DoubaoBatchAdapter(
      doubaoOptionsFromManifest({
        sutId: manifest.sut.id,
        headless: manifest.execution.headless,
        options: manifest.sut.options,
      }),
    );
  }
  if (manifest.sut.adapter === "process") {
    return new ProcessResearchAdapter(processOptionsFromManifest(manifest));
  }
  if (manifest.sut.adapter === "http_api") {
    return new HttpResearchAdapter(httpOptionsFromManifest(manifest));
  }
  throw new Error(`SUT adapter is not implemented yet: ${manifest.sut.adapter}`);
}
