import type { ReactNode } from "react";

/** Formulario: Intro envía. Es la única `<form>` fuera del kit de componentes. */
export function Form({ onSubmit, children }: { onSubmit: () => void; children: ReactNode }) {
  return <form className="ms-form" noValidate onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>{children}</form>;
}
