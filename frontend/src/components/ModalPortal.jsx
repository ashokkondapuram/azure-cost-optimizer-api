import { createPortal } from 'react-dom';

/** Render modals at document body so hub panels cannot clip them. */
export default function ModalPortal({ children }) {
  if (typeof document === 'undefined') return null;
  return createPortal(children, document.body);
}
