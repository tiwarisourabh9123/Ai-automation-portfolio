(function () {
  const chatHistory = [];
  const widgetHTML = `
    <div id="rag-widget-container" class="fixed bottom-5 right-5 z-50 font-sans">
      <button id="rag-toggle-btn" class="bg-amber-500 hover:bg-amber-600 text-stone-950 font-bold px-5 py-3.5 rounded-full shadow-xl transition">
        Ask AI Concierge
      </button>
      <div id="rag-chat-box" class="hidden mt-3 w-80 sm:w-96 bg-white rounded-2xl shadow-2xl border border-stone-200 overflow-hidden flex-col" style="height: 470px;">
        <div class="bg-stone-900 text-white px-4 py-3 flex justify-between items-center">
          <div>
            <p class="font-semibold text-sm">Spice & Flame AI Concierge</p>
            <p class="text-[11px] text-amber-400">Menu, Policies & Table Bookings</p>
          </div>
          <button id="rag-close-btn" class="text-stone-400 hover:text-white text-lg">&times;</button>
        </div>
        <div id="rag-messages" class="flex-1 p-4 overflow-y-auto space-y-3 bg-stone-50 text-sm">
          <div class="bg-white border border-stone-200 p-3 rounded-xl text-stone-700 shadow-sm">
            Hi! Ask me about dishes, allergies, delivery policies, <strong>book a table</strong>, or ask to speak with our desk team.
          </div>
        </div>
        <form id="rag-chat-form" class="border-t border-stone-200 p-2 bg-white flex gap-2">
          <input id="rag-input" type="text" placeholder="Ask menu, book table, or call staff..." required class="flex-1 text-sm px-3 py-2 border border-stone-300 rounded-lg focus:outline-none focus:border-amber-500" />
          <button type="submit" class="bg-stone-900 hover:bg-stone-800 text-white text-sm font-semibold px-4 py-2 rounded-lg">Send</button>
        </form>
      </div>
    </div>`;
  document.body.insertAdjacentHTML("beforeend", widgetHTML);

  const chatBox = document.getElementById("rag-chat-box");
  document.getElementById("rag-toggle-btn").onclick = () => {
    chatBox.classList.toggle("hidden");
    chatBox.classList.toggle("flex");
  };
  document.getElementById("rag-close-btn").onclick = () => {
    chatBox.classList.add("hidden");
    chatBox.classList.remove("flex");
  };

  const messages = document.getElementById("rag-messages");
  function appendMessage(text, isUser, sources = [], showCallButtons = false) {
    const wrapper = document.createElement("div");
    wrapper.className = isUser
      ? "bg-amber-500 text-stone-950 font-medium p-3 rounded-xl ml-8 shadow-sm"
      : "bg-white border border-stone-200 text-stone-800 p-3 rounded-xl mr-6 shadow-sm";
    const textEl = document.createElement("div");
    textEl.textContent = text;
    wrapper.appendChild(textEl);

    if (!isUser && showCallButtons) {
      const row = document.createElement("div");
      row.className = "mt-2.5 flex gap-2";
      row.innerHTML = `
        <a href="tel:+918041239876" class="flex-1 text-center bg-stone-900 hover:bg-stone-800 text-white text-xs font-semibold py-2 rounded-lg">Call Desk</a>
        <a href="https://wa.me/918041239876?text=Hi%20Spice%20%26%20Flame%20Desk%2C%20I%20need%20help." target="_blank" class="flex-1 text-center bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold py-2 rounded-lg">WhatsApp Desk</a>
      `;
      wrapper.appendChild(row);
    }

    if (!isUser && sources.length > 0) {
      const srcDiv = document.createElement("div");
      srcDiv.className = "mt-2 pt-1.5 border-t border-stone-100 text-[11px] text-stone-500";
      srcDiv.textContent = "Sources: " + sources.join(", ");
      wrapper.appendChild(srcDiv);
    }
    messages.appendChild(wrapper);
    messages.scrollTop = messages.scrollHeight;
  }

  const form = document.getElementById("rag-chat-form");
  const input = document.getElementById("rag-input");
  form.onsubmit = async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;
    appendMessage(msg, true);
    input.value = "";
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history: chatHistory }),
      });
      const data = await res.json();
      const reply = data.reply || data.error;
      chatHistory.push({ role: "user", text: msg });
      chatHistory.push({ role: "model", text: reply });
      const needsPhone = /\+91|call|whatsapp|desk|staff|real person/i.test(reply);
      appendMessage(reply, false, data.sources || [], needsPhone);
    } catch {
      appendMessage("Error connecting to AI server.", false);
    }
  };
})();