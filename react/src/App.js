import "./App.css";
import React, { useState, useEffect } from "react";
import PumpIcon from "./PumpIcon";
import { ReactComponent as Logo } from "../src/assets/Logo.svg";
import { ReactComponent as Disconnect } from "../src/assets/Disconnect.svg";
import axios from "axios";
import MessageModal from "./Modal";
function App() {
  const [localDateTime, setLocalDateTime] = useState(""); // 상태 관리
  const [resultData, setResultData] = useState([]);
  // const [isRunning, setIsRunning] = useState(true);
  const [modalData, setModalData] = useState({ title: "", message: "" });

  const resetModalData = () => {
    setModalData({ title: "", message: "" });
  };

  const GetData = async () => {
    try {
      const res = await axios.post("http://127.0.0.1:8000/serial/post/test");
      resetModalData;
      console.log(res);
      if (res.data.status) {
        setResultData(res.data.data);
        setModalData({
          title: "",
          message: "",
        });
      } else {
        //show message
        //시리얼통신에러
        console.log(res.data.data.message);
        setModalData({
          title: "통신오류발생",
          message: res.data.data.message,
        });
      }
    } catch (err) {
      setModalData({
        title: "통신오류발생",
        message: "서버와의 연결이 해제되었습니다",
      });
      console.log(err);
    } finally {
      GetDateTime();
    }
  };

  const changeIcon = (resultData) => {
    Object.entries(resultData).forEach(([key, value]) => {
      const pumpColor = value.pump ? "#64B845" : "#666666";
      const drainColor = value.drain ? "#3FA9F5" : "#E6E6E6";

      document
        .getElementsByName(`pump-icon-${key}`)[0]
        ?.setAttribute("fill", pumpColor);
      document
        .getElementsByName(`drain-icon-${key}`)[0]
        ?.setAttribute("fill", drainColor);
    });
  };

  const GetDateTime = () => {
    const date = new Date();

    const formattedDate = `${
      date.getFullYear() +
      "-" +
      (date.getMonth() + 1).toString().padStart(2, "0") +
      "-" +
      date.getDate().toString().padStart(2, "0") +
      " " +
      date.getHours().toString().padStart(2, "0") +
      ":" +
      date.getMinutes().toString().padStart(2, "0") +
      ":" +
      date.getSeconds().toString().padStart(2, "0")
    }`;

    setLocalDateTime(formattedDate);
  };

  useEffect(() => {
    GetData();
    const dataInterval = setInterval(() => {
      GetData();
    }, 3000); // 10초마다 호출

    const timeInterval = setInterval(() => {
      GetDateTime();
    }, 1000);

    return () => clearInterval(dataInterval, timeInterval);
  }, []);

  const resultDataList = Object.entries(resultData).map(([key, value]) => ({
    id: Number(key),
    ...value,
  }));

  return (
    <div className="App">
      <header className="App-header"></header>
      <div className="title">
        <div className="title-logo">
          <Logo />
        </div>
        <div className="title-container">
          <div className="title-text">펌프 작동 모니터링 시스템</div>
          <div className="title-time">{localDateTime}</div>
        </div>
      </div>
      <div className="content">
        <div className="row">
          {resultDataList.map((data) => (
            <div className="section" key={data.id}>
              <div className="section-form">
                <div className="section-title">{data.id}번 펌프</div>
                <div className="section-content">
                  {data.status ? (
                    <PumpIcon pump={data.pump} drain={data.drain} />
                  ) : (
                    <Disconnect />
                  )}
                  <div className="text-content">
                    <div>펌프 가동</div>
                    <div
                      className="section-value"
                      style={{
                        color: data.status
                          ? data.pump
                            ? "#3FA9F5"
                            : "#000"
                          : "#000", // ON일 때 녹색, OFF일 때 빨간색
                      }}
                    >
                      {data.pump ? "ON" : "OFF"}
                    </div>
                    <span className="line" />
                    <div>배수 가동</div>
                    <div
                      className="section-value"
                      style={{
                        color: data.status
                          ? data.drain
                            ? "#64B845"
                            : "#000"
                          : "#000", // ON일 때 녹색, OFF일 때 빨간색
                      }}
                    >
                      {data.drain ? "ON" : "OFF"}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
      {modalData.title && modalData.message && (
        <MessageModal title={modalData.title} message={modalData.message} />
      )}
    </div>
  );
}

export default App;
