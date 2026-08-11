---
template: landing.html
title: LAESim
---

<section class="landing-hero" aria-labelledby="landing-title">
  <img class="landing-hero__image" src="assets/showcase/laesim-island-scenemap.png" alt="LAESim 岛屿 SceneMap 仿真场景全景" />
  <div class="landing-hero__shade" aria-hidden="true"></div>
  <div class="landing-shell landing-hero__content">
    <p class="landing-affiliation">哈尔滨工业大学（深圳） · 广东省空天网络与智能感知重点实验室</p>
    <p class="landing-kicker">空天地海协同仿真平台</p>
    <h1 id="landing-title">LAESim</h1>
    <p class="landing-hero__lead">在同一个 Unreal Engine 场景中组织无人机、车辆、舰船与卫星，并把天基任务分析、ROS 算法和 ns-3 网络纳入同一套可复现实验流程。</p>
    <div class="landing-actions">
      <a class="landing-button landing-button--primary" href="documentation/">进入文档</a>
      <a class="landing-button landing-button--secondary" href="https://github.com/SANIS-HITSZ/LAESim/tree/V1.5">查看 GitHub</a>
    </div>
    <p class="landing-hero__meta">UE 4.27 · Python API · ROS Noetic · ns-3.48</p>
  </div>
</section>

<section class="landing-facts" aria-label="LAESim 核心能力概览">
  <div class="landing-shell landing-facts__grid">
    <div><strong>4</strong><span>类协同载具</span></div>
    <div><strong>5</strong><span>个独立 RPC 端口</span></div>
    <div><strong>2</strong><span>种通信后端</span></div>
    <div><strong>1</strong><span>套统一场景配置</span></div>
  </div>
</section>

<section class="landing-section landing-section--fleet">
  <div class="landing-shell landing-feature">
    <figure class="landing-feature__media">
      <img src="assets/showcase/laesim-air-space-sea-overview.png" alt="LAESim 场景中的卫星、无人机、车辆与舰船" loading="lazy" />
      <figcaption>同一岛屿场景中的卫星、无人机、车辆与舰船</figcaption>
    </figure>
    <div class="landing-feature__copy">
      <p class="landing-eyebrow">统一载具体系</p>
      <h2>从单类仿真扩展到空天地海协同</h2>
      <p>LAESim 的 <code>AirGround</code> 模式允许不同载具共享场景、传感器与任务时间线，同时保持各自独立的控制接口和 RPC 端口。</p>
      <ul class="landing-checklist">
        <li><strong>无人机</strong><span>SimpleFlight 与多机控制</span></li>
        <li><strong>车辆</strong><span>PhysXCar 与地面任务</span></li>
        <li><strong>舰船</strong><span>简化三自由度水面运动</span></li>
        <li><strong>卫星</strong><span>显示模型、真实轨道与任务分析</span></li>
      </ul>
      <a class="landing-text-link" href="laesim_features/">查看载具与接口 →</a>
    </div>
  </div>
</section>

<section class="landing-section landing-section--map">
  <div class="landing-shell">
    <div class="landing-section__heading">
      <p class="landing-eyebrow">SceneMap</p>
      <h2>让卫星图成为可计算的仿真场景</h2>
      <p>将图片加载为可碰撞平面地图，建立像素、局部米制坐标与 GPS 之间的转换关系，让载具按真实地理位置出生和协同。</p>
    </div>
    <div class="landing-pipeline" aria-label="SceneMap 数据流程">
      <div><span>01</span><strong>导入图片</strong><small>任意长宽比的卫星图或任务地图</small></div>
      <b aria-hidden="true">→</b>
      <div><span>02</span><strong>设置比例尺</strong><small>定义每个像素对应的实际距离</small></div>
      <b aria-hidden="true">→</b>
      <div><span>03</span><strong>GPS 配准</strong><small>通过 GeoReference 对齐经纬度</small></div>
      <b aria-hidden="true">→</b>
      <div><span>04</span><strong>运行任务</strong><small>按像素、米制坐标或 GPS 部署载具</small></div>
    </div>
  </div>
</section>

<section class="landing-section landing-section--workflow">
  <div class="landing-shell landing-workflow">
    <div>
      <p class="landing-eyebrow">天基任务</p>
      <h2>真实任务几何与 UE 演示坐标解耦</h2>
      <p>TLE/SGP4、CSV 或可选 Orekit 后端负责真实星历、可见窗口、覆盖与重访；UE 中的卫星模型只显示缩放轨迹，NetworkSim 使用真实斜距完成链路预算。</p>
      <a class="landing-text-link" href="space_mission_bridge/">查看天基任务桥接 →</a>
    </div>
    <ol>
      <li><span>1</span><div><strong>轨道传播</strong><p>读取 TLE 或外部星历，生成统一时标下的卫星状态。</p></div></li>
      <li><span>2</span><div><strong>任务分析</strong><p>计算多目标 access、覆盖窗口、重访与最佳卫星。</p></div></li>
      <li><span>3</span><div><strong>显示同步</strong><p>按可控比例驱动 UE 中的 SimpleSatellite。</p></div></li>
      <li><span>4</span><div><strong>通信联动</strong><p>按真实斜距、SNR、带宽和误码模型控制星地与星间链路。</p></div></li>
    </ol>
  </div>
</section>

<section class="landing-section landing-section--showcase">
  <div class="landing-shell">
    <div class="landing-section__heading">
      <p class="landing-eyebrow">仿真画面</p>
      <h2>从单类编队到多域协同</h2>
      <p>以下画面均来自 LAESim 当前开发版本，用于展示不同类型载具在统一岛屿场景中的运行状态。</p>
    </div>
    <div class="landing-gallery">
      <figure>
        <img src="assets/showcase/laesim-uav-ground-team.png" alt="三架无人机与三辆车辆组成的空地协同编队" loading="lazy" />
        <figcaption><strong>空地协同</strong><span>多无人机与多车辆联合部署</span></figcaption>
      </figure>
      <figure>
        <img src="assets/showcase/laesim-satellite-formation.png" alt="两颗卫星在岛屿场景上空编队运行" loading="lazy" />
        <figcaption><strong>空间载具</strong><span>卫星编队与三维运动控制</span></figcaption>
      </figure>
      <figure>
        <img src="assets/showcase/laesim-ship-formation.png" alt="三艘舰船在海面编队运行" loading="lazy" />
        <figcaption><strong>海上编队</strong><span>多舰船水面运动仿真</span></figcaption>
      </figure>
    </div>
    <a class="landing-text-link" href="simulation_cases/">查看全部仿真案例 →</a>
  </div>
</section>

<section class="landing-section landing-section--demo">
  <div class="landing-shell landing-demo">
    <div class="landing-demo__copy">
      <p class="landing-eyebrow">视频演示</p>
      <h2>查看 LAESim 场景运行效果</h2>
      <p>通过实际录制画面了解岛屿环境、多类型载具和协同场景的整体效果。</p>
    </div>
    <video class="landing-demo__video" controls preload="metadata" playsinline poster="assets/showcase/laesim-air-space-sea-overview.png">
      <source src="assets/showcase/laesim-platform-demo.mp4" type="video/mp4" />
      当前浏览器不支持 HTML5 视频播放。
    </video>
  </div>
</section>

<section class="landing-section landing-section--network">
  <div class="landing-shell">
    <div class="landing-section__heading landing-section__heading--light">
      <p class="landing-eyebrow">ROS + ns-3</p>
      <h2>把通信条件带入协同算法</h2>
      <p>保留理想通信作为基线，或启用 ns-3 模拟 Wi-Fi ad hoc、OLSR/AODV；星地与星间业务可改用真实斜距逻辑链路。</p>
    </div>
    <div class="landing-network-flow" aria-label="LAESim 与 ROS、ns-3 的集成关系">
      <div><small>Windows</small><strong>LAESim / UE4</strong><span>物理、画面、传感器与载具位置</span></div>
      <b aria-hidden="true">→</b>
      <div><small>WSL2</small><strong>ROS Noetic</strong><span>控制、状态和协同应用消息</span></div>
      <b aria-hidden="true">→</b>
      <div><small>可选后端</small><strong>ns-3.48</strong><span>无线链路、路由和网络指标</span></div>
    </div>
    <div class="landing-network-actions">
      <a class="landing-button landing-button--light" href="laesim_wsl_ros_ns3/">查看集成与安装</a>
      <a class="landing-text-link landing-text-link--light" href="simulation_cases/">查看验证案例 →</a>
    </div>
  </div>
</section>

<section class="landing-section landing-section--workflow">
  <div class="landing-shell landing-workflow">
    <div>
      <p class="landing-eyebrow">可复现工程</p>
      <h2>从源码构建到实验验证</h2>
    </div>
    <ol>
      <li><span>1</span><div><strong>选择配置</strong><p>从混合载具、SceneMap 和传感器模板开始。</p></div></li>
      <li><span>2</span><div><strong>启动场景</strong><p>在 UE 4.27 中运行 LAESim 并确认各 RPC 端口。</p></div></li>
      <li><span>3</span><div><strong>连接算法</strong><p>使用 Python API，或在 WSL2 中连接 ROS Noetic。</p></div></li>
      <li><span>4</span><div><strong>加入网络</strong><p>按实验需要在理想通信与 ns-3 后端之间切换。</p></div></li>
    </ol>
  </div>
</section>

<section class="landing-section landing-section--team" id="team" aria-labelledby="team-title">
  <div class="landing-shell">
    <div class="landing-section__heading">
      <p class="landing-eyebrow">团队与联系</p>
      <h2 id="team-title">由空天网络与智能感知重点实验室开发维护</h2>
      <p>LAESim 由哈尔滨工业大学（深圳）广东省空天网络与智能感知重点实验室持续开发，欢迎试用、反馈问题并开展科研合作。</p>
    </div>
    <div class="landing-team__grid">
      <section class="landing-team__group" aria-labelledby="team-leads">
        <p class="landing-team__role" id="team-leads">实验室负责人</p>
        <div class="landing-team__names">
          <strong>张霆廷</strong>
          <strong>梁天豪</strong>
        </div>
      </section>
      <section class="landing-team__group" aria-labelledby="team-contributors">
        <p class="landing-team__role" id="team-contributors">主要贡献者</p>
        <div class="landing-team__names">
          <strong>平雨奇</strong>
          <strong>吴俊炜</strong>
          <strong>雷光宇</strong>
        </div>
      </section>
    </div>
    <div class="landing-team__links">
      <a class="landing-text-link" href="https://github.com/SANIS-HITSZ/LAESim/blob/V1.5/CONTRIBUTORS.md">查看团队与联系方式 →</a>
      <a class="landing-text-link" href="https://github.com/SANIS-HITSZ/LAESim/issues">提出问题或合作建议 →</a>
    </div>
  </div>
</section>

<section class="landing-cta">
  <div class="landing-shell landing-cta__inner">
    <div>
      <p class="landing-eyebrow">开始使用 LAESim</p>
      <h2>构建你的空天地海协同场景</h2>
    </div>
    <div class="landing-actions">
      <a class="landing-button landing-button--primary" href="documentation/">阅读文档</a>
      <a class="landing-button landing-button--outline" href="https://github.com/SANIS-HITSZ/LAESim/tree/V1.5">获取源码</a>
    </div>
  </div>
</section>
