import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Btn } from "./Btn";
import { Notice } from "./Fields";

function Failed({ error, retry }: { error: Error; retry: () => void }) {
  const { t } = useTranslation();
  return (
    <Notice tone="danger" title={t("Esta pantalla ha fallado")}>
      {t("El resto de la aplicación sigue funcionando: puedes reintentar o ir a otra pantalla.")} <span className="ms-data">{error.message}</span>{" "}
      <Btn kind="link" onClick={retry}>{t("Reintentar")}</Btn>
    </Notice>
  );
}

/** A screen that throws while rendering shows a danger notice with «Reintentar» instead of leaving the whole application blank.
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
    console.error("MimirSynth: la pantalla ha fallado", error, info.componentStack);
  }

  render() {
    return this.state.error ? <Failed error={this.state.error} retry={() => this.setState({ error: null })} /> : this.props.children;
  }
}
