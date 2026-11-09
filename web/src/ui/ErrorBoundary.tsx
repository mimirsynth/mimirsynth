import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Btn } from "./Btn";
import { Notice } from "./Fields";
import { isChunkLoadError, reloadForUpdate } from "./chunkReload";

function Failed({ error, retry }: { error: Error; retry: () => void }) {
  const { t } = useTranslation();
  if (isChunkLoadError(error)) {
    // Retrying asks again for a chunk the new version no longer has: only a reload gets the new version (#429).
    return (
      <Notice tone="warn" title={t("MimirSynth se ha actualizado")}>
        {t("Esta pantalla es de la versión anterior. Recarga la página para cargar la nueva.")}{" "}
        <Btn kind="link" onClick={() => window.location.reload()}>{t("Recargar")}</Btn>
      </Notice>
    );
  }
  return (
    <Notice tone="danger" title={t("Esta pantalla ha fallado")}>
      {t("El resto de la aplicación sigue funcionando: puedes reintentar o ir a otra pantalla.")} <span className="ms-data">{error.message}</span>{" "}
      <Btn kind="link" onClick={retry}>{t("Reintentar")}</Btn>
    </Notice>
  );
}

/** A screen that throws while rendering shows a danger notice with «Reintentar» instead of leaving the whole application blank.
 *  A screen whose code could not be loaded means the application was updated: the page reloads once by itself and, if that already
 *  happened, the notice says so and offers «Recargar» (#429).
 *  `resetKey` (the route and the brain): going elsewhere clears the failure. */
export class ErrorBoundary extends Component<{ resetKey: string; children: ReactNode }, { error: Error | null; key: string }> {
  state = { error: null as Error | null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  static getDerivedStateFromProps(props: { resetKey: string }, state: { error: Error | null; key: string }) {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (isChunkLoadError(error) && reloadForUpdate()) return;
    console.error("MimirSynth: la pantalla ha fallado", error, info.componentStack);
  }

  render() {
    return this.state.error ? <Failed error={this.state.error} retry={() => this.setState({ error: null })} /> : this.props.children;
  }
}
