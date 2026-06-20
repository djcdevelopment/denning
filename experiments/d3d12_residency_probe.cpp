// denning D3D12 residency-priority probe (I-3 defense feasibility)
//
// Question: on this Intel Arc B70 / Win10 WDDM driver, does D3D12 residency
// priority (SetResidencyPriority MAXIMUM + MakeResident) actually protect an
// allocation from involuntary eviction under VRAM oversubscription -- i.e. is the
// "pinned arena" denning needs even feasible via the documented Windows knob?
//
// Each instance allocates --size-gb of DEFAULT-heap VRAM on --adapter at --priority
// (max|normal), MakeResident, then samples THIS process's per-adapter LOCAL vs
// NON_LOCAL usage every second for --hold-s. Run two instances on the SAME adapter
// so together they oversubscribe the card:
//   A = MAX-priority "arena", B = NORMAL-priority "aggressor".
// If A stays LOCAL (non_local ~0) while B is demoted (non_local rises) -> priority
// defends -> the arena is feasible. If A is demoted too -> priority is insufficient
// on this driver -> the arena needs harder pinning (a real finding either way).
//
// Build (from a VS x64 dev prompt):  cl /EHsc /O2 d3d12_residency_probe.cpp

#include <windows.h>
#include <dxgi1_6.h>
#include <d3d12.h>
#include <wrl/client.h>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
#pragma comment(lib, "d3d12.lib")
#pragma comment(lib, "dxgi.lib")

static double GB(UINT64 b) { return (double)b / (1024.0 * 1024.0 * 1024.0); }

int main(int argc, char** argv) {
    int adapterIdx = 1;
    double sizeGb = 18.0, chunkGb = 2.0;
    int holdS = 45;
    bool maxPri = true;
    const char* tag = "probe";
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--adapter" && i + 1 < argc) adapterIdx = atoi(argv[++i]);
        else if (a == "--size-gb" && i + 1 < argc) sizeGb = atof(argv[++i]);
        else if (a == "--chunk-gb" && i + 1 < argc) chunkGb = atof(argv[++i]);
        else if (a == "--hold-s" && i + 1 < argc) holdS = atoi(argv[++i]);
        else if (a == "--priority" && i + 1 < argc) maxPri = (std::string(argv[++i]) == "max");
        else if (a == "--tag" && i + 1 < argc) tag = argv[++i];
    }

    ComPtr<IDXGIFactory4> factory;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory)))) { printf("[%s] factory fail\n", tag); return 2; }
    ComPtr<IDXGIAdapter1> adapter;
    if (factory->EnumAdapters1(adapterIdx, &adapter) == DXGI_ERROR_NOT_FOUND) {
        printf("[%s] adapter %d not found\n", tag, adapterIdx); return 2;
    }
    DXGI_ADAPTER_DESC1 desc; adapter->GetDesc1(&desc);
    wprintf(L"[%hs] adapter %d: %s (LUID %08x:%08x, dedicated %.1f GB)\n",
            tag, adapterIdx, desc.Description,
            (unsigned)desc.AdapterLuid.HighPart, (unsigned)desc.AdapterLuid.LowPart,
            GB(desc.DedicatedVideoMemory));
    fflush(stdout);

    ComPtr<IDXGIAdapter3> adapter3; adapter.As(&adapter3);
    ComPtr<ID3D12Device> device;
    if (FAILED(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device)))) {
        printf("[%s] device fail\n", tag); return 2;
    }
    ComPtr<ID3D12Device1> device1; device.As(&device1);

    printf("[%s] priority=%s, allocating %.1f GB in %.1f GB chunks ...\n",
           tag, maxPri ? "MAX" : "NORMAL", sizeGb, chunkGb);
    fflush(stdout);

    std::vector<ComPtr<ID3D12Resource>> blocks;
    D3D12_HEAP_PROPERTIES hp = {}; hp.Type = D3D12_HEAP_TYPE_DEFAULT;
    double alloc = 0; int residentFails = 0;
    while (alloc + chunkGb <= sizeGb + 1e-6) {
        D3D12_RESOURCE_DESC rd = {};
        rd.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
        rd.Width = (UINT64)(chunkGb * 1024.0 * 1024.0 * 1024.0);
        rd.Height = 1; rd.DepthOrArraySize = 1; rd.MipLevels = 1;
        rd.Format = DXGI_FORMAT_UNKNOWN; rd.SampleDesc.Count = 1;
        rd.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR; rd.Flags = D3D12_RESOURCE_FLAG_NONE;
        ComPtr<ID3D12Resource> res;
        HRESULT hr = device->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE, &rd,
                        D3D12_RESOURCE_STATE_COMMON, nullptr, IID_PPV_ARGS(&res));
        if (FAILED(hr)) { printf("[%s] CreateCommittedResource failed at %.1f GB (hr=0x%08x)\n", tag, alloc, (unsigned)hr); break; }
        if (maxPri) {
            ID3D12Pageable* pg = res.Get();
            D3D12_RESIDENCY_PRIORITY pr = D3D12_RESIDENCY_PRIORITY_MAXIMUM;
            device1->SetResidencyPriority(1, &pg, &pr);
        }
        ID3D12Pageable* pg = res.Get();
        if (FAILED(device->MakeResident(1, &pg))) residentFails++;
        blocks.push_back(res);
        alloc += chunkGb;
    }
    printf("[%s] allocated %.1f GB (MakeResident fails: %d). holding %ds:\n", tag, alloc, residentFails, holdS);
    fflush(stdout);

    for (int s = 0; s < holdS; s++) {
        DXGI_QUERY_VIDEO_MEMORY_INFO loc = {}, non = {};
        adapter3->QueryVideoMemoryInfo(0, DXGI_MEMORY_SEGMENT_GROUP_LOCAL, &loc);
        adapter3->QueryVideoMemoryInfo(0, DXGI_MEMORY_SEGMENT_GROUP_NON_LOCAL, &non);
        printf("[%s] t=%2ds LOCAL_usage=%.2f GB (budget %.2f) | NON_LOCAL_usage=%.2f GB\n",
               tag, s, GB(loc.CurrentUsage), GB(loc.Budget), GB(non.CurrentUsage));
        fflush(stdout);
        Sleep(1000);
    }
    printf("[%s] done (held %.1f GB).\n", tag, alloc);
    return 0;
}
