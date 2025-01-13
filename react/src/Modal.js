import React, { useEffect } from "react";
import "./Modal.css";
import { ReactComponent as Disconnect } from "../src/assets/Disconnect.svg";

function Modal({ title, message }) {
  return (
    <div className="modal-wrap">
      <div className="modal">
        <div className="modal-content">
          <div className="modal-title">{title}</div>
          <div className="modal-icon">
            <Disconnect />
          </div>
          <div className="modal-message">{message}</div>
        </div>
      </div>
    </div>
  );
}

export default Modal;
